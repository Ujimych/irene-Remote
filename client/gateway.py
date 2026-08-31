import asyncio
import json
import logging
import re
import ssl

import RPi.GPIO as GPIO
import websockets

class Gateway:

    LISTEN_TIMEOUT = 60

    def __init__(self, in_config, in_path, in_voiceRecorder, in_audioPlayer, in_mpdPlayer, in_volumeControl):
        self.host = in_config["host"]
        self.port = in_config["port"]
        self.path = in_path
        self.voiceRecorder = in_voiceRecorder
        self.audioPlayer = in_audioPlayer
        self.mpdPlayer = in_mpdPlayer
        self.volumeControl = in_volumeControl
        self.samplerate = in_config["samplerate_input"]
        self.websocket = None
        self.task_listen_incoming = None
        self.task_listen_second_connection = None
        self.tasks_listen_recorder = []
        self.listen_mode = False
        self.listen_timer_task = None
        self.listen_ack_pending = False
        self.listen_confirmation_pending = False
        self.command_pending = False
        self.command_blink_task = None
        self.audio_playing = False
        self.unmute_pending = False
        self.audio_playback_lock = asyncio.Lock()
        self.audio_playback_count = 0
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self._logger = logging.getLogger("Gateway")
        self._logger.setLevel(logging.DEBUG)
        if not self._logger.handlers:
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)
        GPIO.setmode(GPIO.BCM)
        self.LED_PIN = 13
        GPIO.setup(self.LED_PIN, GPIO.OUT)
        self.led_on = True
        GPIO.output(self.LED_PIN, GPIO.HIGH)
        self._logger.debug("Светодиод включен")

    def start_command_blink(self):
        self.command_pending = True
        if self.command_blink_task is None:
            self._logger.debug("Начинаем мигание: ожидание ответа от сервера.")
            self.command_blink_task = asyncio.create_task(self._command_blink())

    async def stop_command_blink(self):
        self.command_pending = False
        if self.command_blink_task is not None:
            self.command_blink_task.cancel()
            try:
                await self.command_blink_task
            except asyncio.CancelledError:
                pass
            self.command_blink_task = None
        if self.websocket is not None:
            self.led_on = False
            GPIO.output(self.LED_PIN, GPIO.LOW)
            self._logger.debug("Ответ получен. Мигание остановлено, светодиод выключен.")

    async def _command_blink(self):
        try:
            while self.command_pending:
                GPIO.output(self.LED_PIN, GPIO.HIGH)
                await asyncio.sleep(0.5)
                if not self.command_pending:
                    break
                GPIO.output(self.LED_PIN, GPIO.LOW)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise

    async def start_listen_mode(self):
        if self.listen_mode:
            self._logger.debug("Режим 'Слушай' уже активен. Перезапускаем таймер.")
            if self.listen_timer_task is not None:
                self.listen_timer_task.cancel()
                try:
                    await self.listen_timer_task
                except asyncio.CancelledError:
                    pass
                self.listen_timer_task = None
        else:
            self.listen_mode = True
            self._logger.info("Режим 'Слушай' активирован.")
            if self.mpdPlayer is not None:
                mpd_result = self.mpdPlayer.start_listen_mode()
                self._logger.debug(f"MPD перед режимом 'Слушай' воспроизводился: {mpd_result}")
        self.start_command_blink()
        self.listen_timer_task = asyncio.create_task(self._listen_timeout())

    async def _listen_timeout(self):
        try:
            self._logger.info(f"Ожидание голосовой команды: {self.LISTEN_TIMEOUT} секунд.")
            await asyncio.sleep(self.LISTEN_TIMEOUT)
            if not self.listen_mode:
                return
            self._logger.info("Время ожидания режима 'Слушай' истекло.")
            await self.finish_listen_mode()
        except asyncio.CancelledError:
            self._logger.debug("Таймер режима 'Слушай' отменён.")
            raise

    async def finish_listen_mode(self, resume_mpd=True):
        was_listen_mode = self.listen_mode
        self.listen_mode = False
        self.listen_confirmation_pending = False
        current_task = asyncio.current_task()
        if self.listen_timer_task is not None and self.listen_timer_task is not current_task:
            self.listen_timer_task.cancel()
            try:
                await self.listen_timer_task
            except asyncio.CancelledError:
                pass
        self.listen_timer_task = None
        if not was_listen_mode:
            return
        await self.stop_command_blink()
        if self.mpdPlayer is not None:
            if resume_mpd:
                self._logger.debug("Завершаем режим 'Слушай'. Проверяем необходимость восстановления MPD.")
                self.mpdPlayer.finish_listen_mode()
            else:
                self._logger.debug("Режим 'Слушай' завершён без восстановления MPD.")
                self.mpdPlayer.cancel_listen_mode()
        self._logger.info("Режим 'Слушай' завершён.")

    async def connect(self):
        while True:
            try:
                self.websocket = await websockets.connect(f"wss://{self.host}:{self.port}{self.path}", ssl=self.ssl_context)
                self._logger.debug("Подключен к серверу!")
                await self.send_message(json.dumps({"type": "negotiate/request", "protocols": [["in.text-direct", "in.text-indirect"], ["out.audio.link"], ["out.tts.serverside", "out.text-plain"], ["in.stt.serverside", "in.stt.clientside", "in.text-indirect"], ["in.mute"], ["out.volume"], ["out.listen"]]}))
                await self.wait_first_response()
                self.command_pending = False
                self.listen_confirmation_pending = False
                if self.command_blink_task is not None:
                    await self.stop_command_blink()
                if self.led_on:
                    self._logger.debug("Светодиод выключен")
                    self.led_on = False
                    GPIO.output(self.LED_PIN, GPIO.LOW)
                if self.task_listen_incoming is None:
                    self._logger.debug("Создаем задачу приема сообщений.")
                    self.task_listen_incoming = asyncio.create_task(self.listen_for_incoming_messages())
                break
            except OSError as e:
                self.command_pending = False
                if self.command_blink_task is not None:
                    self.command_blink_task.cancel()
                    try:
                        await self.command_blink_task
                    except asyncio.CancelledError:
                        pass
                    self.command_blink_task = None
                self.led_on = True
                GPIO.output(self.LED_PIN, GPIO.HIGH)
                self._logger.warning(f"Сервер недоступен: {e}. Повторная попытка через 5 секунд...")
                await asyncio.sleep(5)
            except Exception as e:
                self.command_pending = False
                if self.command_blink_task is not None:
                    self.command_blink_task.cancel()
                    try:
                        await self.command_blink_task
                    except asyncio.CancelledError:
                        pass
                    self.command_blink_task = None
                self.led_on = True
                GPIO.output(self.LED_PIN, GPIO.HIGH)
                self._logger.exception(f"Ошибка соединения с сервером: {e}. Повторная попытка через 5 секунд...")
                await asyncio.sleep(5)

    async def close(self):
        self.command_pending = False
        self.listen_confirmation_pending = False
        if self.command_blink_task is not None:
            self.command_blink_task.cancel()
            try:
                await self.command_blink_task
            except asyncio.CancelledError:
                pass
            self.command_blink_task = None
        if self.listen_mode:
            await self.finish_listen_mode(resume_mpd=False)
        if self.websocket is not None:
            try:
                await self.websocket.close()
                self._logger.debug("Отключен от сервера.")
            except Exception as e:
                self._logger.debug(f"Ошибка закрытия WebSocket: {e}")
            finally:
                self.websocket = None
        self.led_on = True
        GPIO.output(self.LED_PIN, GPIO.HIGH)

    async def send_message(self, in_message):
        self._logger.debug(f"send_message: {in_message}")
        await self.websocket.send(in_message)
        self._logger.debug(f"отправил: {in_message}")

    async def receive_message(self):
        try:
            return await self.websocket.recv()
        except websockets.ConnectionClosedError:
            self._logger.debug("Соединение неожиданно прервано.")
            self.command_pending = False
            self.listen_confirmation_pending = False

            if self.command_blink_task is not None:
                self.command_blink_task.cancel()
                try:
                    await self.command_blink_task
                except asyncio.CancelledError:
                    pass
                self.command_blink_task = None

            self.led_on = True
            GPIO.output(self.LED_PIN, GPIO.HIGH)
            self._logger.debug("Светодиод включен")
            raise

    async def wait_first_response(self):
        first_response = await self.receive_message()

        if first_response is not None:
            self._logger.debug(f"Первый ответ: {first_response}")
            await self.send_message(json.dumps({"type": "in.text-direct/text", "text": "соединение установлено"}))

    async def listen_for_incoming_messages(self):
        while True:
            try:
                response = await self.receive_message()
                get_data = json.loads(response)

                self._logger.debug(f"ПОЛНОЕ ВХОДЯЩЕЕ СООБЩЕНИЕ: {get_data}")

                if get_data.get("text") is not None:
                    self._logger.debug(f"получено >>> text: {get_data.get('text')}")

                if get_data.get("altText") is not None:
                    self._logger.debug(f"получено >>> altText: {get_data.get('altText')}")

                type_message = get_data.get("type")

                if type_message is not None:
                    if type_message == "in.stt.serverside/processed":
                        text = get_data.get("text")
                        if text:
                            self._logger.debug(f"Обработка голосовой команды: {text}")
                            self.start_command_blink()
                            asyncio.create_task(self.handle_voice_command(text))

                    if type_message == "in.mute/mute":
                        self.unmute_pending = False
                        self._logger.debug("Запись приостановлена.")
                        self.voiceRecorder.resume(False)

                    if type_message == "in.mute/unmute":
                        if self.audio_playing:
                            self._logger.debug("Получена команда возобновления записи, но воспроизведение ещё продолжается. Возобновление отложено.")
                            self.unmute_pending = True
                        else:
                            self._logger.debug("Запись возобновлена.")
                            self.voiceRecorder.resume(True)

                    if type_message == "out.volume/command":
                        self._logger.info(f"VOLUME RX: typeMessage={type_message!r}, get_data={get_data!r}")
                        self.start_command_blink()
                        asyncio.create_task(self.handle_volume_command(get_data))

                    if type_message == "out.listen/command":
                        self._logger.info(f"LISTEN RX: typeMessage={type_message!r}, get_data={get_data!r}")
                        asyncio.create_task(self.handle_listen_command(get_data))

                    if type_message == "in.stt.serverside/ready":
                        self.task_listen_second_connection = asyncio.create_task(self.handle_connection(get_data.get("path"), self.samplerate))

                    if "out.audio.link/playback-request" in type_message:
                        asyncio.create_task(self.play_response_audio(get_data))

            except websockets.ConnectionClosedError:
                self._logger.debug("Соединение потеряно. Повторное подключение...")
                self.command_pending = False
                self.listen_confirmation_pending = False

                if self.command_blink_task is not None:
                    self.command_blink_task.cancel()
                    try:
                        await self.command_blink_task
                    except asyncio.CancelledError:
                        pass
                    self.command_blink_task = None

                self.led_on = True
                GPIO.output(self.LED_PIN, GPIO.HIGH)
                self._logger.debug("Светодиод включен")
                self.voiceRecorder.resume(False)

                for task in self.tasks_listen_recorder:
                    task.cancel()
                self.tasks_listen_recorder.clear()

                await self.reconnect()

    async def handle_listen_command(self, data):
        command_id = data.get("commandId")
        self._logger.info(f"LISTEN: получена команда 'Слушай', commandId={command_id!r}")

        try:
            await self.start_listen_mode()
            await self.stop_command_blink()
            self.listen_ack_pending = True
            self._logger.debug("LISTEN: ожидаем подтверждающее аудио от сервера.")

            response = {"type": "out.listen/result", "commandId": command_id, "success": True}
            await self.send_message(json.dumps(response))
            self._logger.debug(f"LISTEN: результат отправлен: {response}")

        except Exception as e:
            self._logger.exception(f"Ошибка обработки команды 'Слушай': {e}")
            self.listen_ack_pending = False
            response = {"type": "out.listen/result", "commandId": command_id, "success": False}

            try:
                await self.send_message(json.dumps(response))
            except Exception as send_error:
                self._logger.exception(f"LISTEN: не удалось отправить результат ошибки: {send_error}")

            await self.stop_command_blink()

    async def play_response_audio(self, data):
        self.audio_playback_count += 1
        self.audio_playing = True
        self._logger.debug(f"Добавлено аудио в очередь воспроизведения. Всего активных/ожидающих: {self.audio_playback_count}")

        try:
            async with self.audio_playback_lock:
                self._logger.debug("Получен доступ к очереди воспроизведения.")
                await asyncio.to_thread(self.audioPlayer.play, self, data.get("playbackId"), data.get("url"), self.mpdPlayer)
        except Exception as e:
            self._logger.exception(f"Ошибка воспроизведения ответа: {e}")
        finally:
            self.audio_playback_count -= 1
            self._logger.debug(f"Обработка аудио завершена. Осталось активных/ожидающих: {self.audio_playback_count}")

            if self.audio_playback_count > 0:
                self.audio_playing = True
                self._logger.debug("Есть следующее аудио в очереди. Запись пока остаётся приостановленной.")
                return

            self.audio_playback_count = 0
            self.audio_playing = False
            self._logger.debug("Вся очередь воспроизведения завершена.")

            if self.unmute_pending:
                self.unmute_pending = False
                self._logger.debug("Вся очередь аудио завершена. Выполняем отложенное возобновление записи.")
                self.voiceRecorder.resume(True)
                self._logger.debug("Запись возобновлена.")

            if self.listen_mode and self.listen_ack_pending:
                self.listen_ack_pending = False
                self._logger.info("Получено подтверждение готовности для режима 'Слушай'. Режим продолжается.")
                await self.stop_command_blink()
                return

            if self.listen_mode:
                self._logger.info("Получен звуковой ответ сервера на команду пользователя. Завершаем режим 'Слушай'.")
                await self.finish_listen_mode(resume_mpd=True)
            else:
                await self.stop_command_blink()

    async def reconnect(self):
        if self.task_listen_second_connection is not None:
            self._logger.debug("Удаляем старое second_connection.")
            self.task_listen_second_connection.cancel()
            self.task_listen_second_connection = None

        if self.listen_mode:
            await self.finish_listen_mode(resume_mpd=True)

        self.listen_confirmation_pending = False

        while True:
            try:
                await self.connect()
                break
            except Exception as e:
                self._logger.exception(f"Повторное подключение не удалось: {e}. Повторная попытка...")
                await asyncio.sleep(5)

    async def handle_connection(self, in_path, in_sample_rate):
        async with websockets.connect(f"wss://{self.host}:{self.port}{in_path}?sample_rate={in_sample_rate}", ssl=self.ssl_context) as websocket:
            self._logger.debug("Дополнительное соединение!")
            tasks = [asyncio.create_task(self.voiceRecorder.producer()), asyncio.create_task(self.voiceRecorder.consumer(websocket))]
            self.tasks_listen_recorder.extend(tasks)
            await asyncio.gather(*tasks)

    async def send_text_for_speech(self, text):
        if self.websocket is None:
            self._logger.warning("Невозможно отправить текст: WebSocket не подключен.")
            return False

        try:
            message = {"type": "in.text-direct/text", "text": text}
            self._logger.debug(f"Отправляем текст для озвучивания: {text!r}")
            await self.send_message(json.dumps(message))
            return True

        except Exception as e:
            self._logger.exception(f"Ошибка отправки текста для озвучивания: {e}")
            return False

    async def handle_voice_command( self, text ):
        if self.volumeControl is None:
            self._logger.warning( "VolumeControl не подключен." )
            await self.stop_command_blink()
            return False
        if text is None:
            await self.stop_command_blink()
            return False
        text = text.strip().lower()
        self._logger.debug( f"Разбор голосовой команды: {text!r}" )
        if text in ( "назови уровень громкости", "назови уровень", "какая громкость", "какой уровень громкости", "уровень громкости" ):
            self._logger.info( "Команда: назвать уровень громкости." )
            current_percent = self.volumeControl.get_volume_percent()
            if current_percent is None:
                await self.send_text_for_speech( "не удалось определить уровень громкости" )
                return False
            self._logger.info( f"Текущая громкость: {current_percent}%" )
            await self.send_text_for_speech( f"громкость {current_percent} процентов" )
            return True
        volume_match = re.fullmatch( r"громкость\s+(\d{1,3})(?:\s+процент(?:а|ов)?)?", text )
        if volume_match:
            percent = int( volume_match.group(1) )
            if percent > 100:
                self._logger.warning( f"Некорректный уровень громкости: {percent}%" )
                await self.send_text_for_speech( "уровень громкости должен быть от нуля до ста процентов" )
                return False
            self._logger.info( f"Команда установки громкости: {percent}%" )
            success = self.volumeControl.set_volume_percent( percent )
            if success:
                await self.send_text_for_speech( "готово" )
            else:
                await self.send_text_for_speech( "не удалось изменить громкость" )
            return success
        if text == "громче":
            self._logger.info( "Команда громкости: громче" )
            success = self.volumeControl.volume_up()
            return success
        if text == "тише":
            self._logger.info( "Команда громкости: тише" )
            success = self.volumeControl.volume_down()
            return success
        await self.stop_command_blink()
        return False

    async def handle_volume_command(self, data):
        command_id = data.get("commandId")
        command = data.get("command")
        value = data.get("value")

        self._logger.debug(f"Обработка out.volume: commandId={command_id}, command={command}, value={value}")

        result = {"commandId": command_id, "success": False}

        if self.volumeControl is None:
            self._logger.warning("VolumeControl не подключен.")
            await self.send_message(json.dumps({"type": "out.volume/result", **result}))
            await self.stop_command_blink()
            return

        try:
            if command == "up":
                success = self.volumeControl.volume_up()
            elif command == "down":
                success = self.volumeControl.volume_down()
            elif command == "set":
                success = self.volumeControl.set_volume_percent(value)
            elif command == "min":
                success = self.volumeControl.volume_min()
            elif command == "middle":
                success = self.volumeControl.volume_middle()
            elif command == "max":
                success = self.volumeControl.volume_max()
            elif command == "mute":
                success = self.volumeControl.volume_mute()
            elif command == "unmute":
                success = self.volumeControl.volume_unmute()
            else:
                self._logger.warning(f"Неизвестная команда громкости: {command}")
                success = False

            self._logger.debug(f"Результат volumeControl: success={success!r}, type={type(success).__name__}")

            result["success"] = bool(success)

            if success:
                current_volume = self.volumeControl.get_volume_percent()
                if current_volume is not None:
                    result["volume"] = current_volume

            response = {"type": "out.volume/result", **result}
            self._logger.debug(f"ОТПРАВЛЯЕМ РЕЗУЛЬТАТ VOLUME: {response}")
            await self.send_message(json.dumps(response))
            self._logger.debug(f"РЕЗУЛЬТАТ VOLUME ОТПРАВЛЕН: commandId={command_id}")

        except Exception as e:
            self._logger.exception(f"Ошибка обработки команды громкости: {e}")
            result["success"] = False
            response = {"type": "out.volume/result", **result}
            self._logger.debug(f"ОТПРАВЛЯЕМ ОШИБКУ VOLUME: {response}")
            await self.send_message(json.dumps(response))

        finally:
            await self.stop_command_blink()
