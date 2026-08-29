import asyncio
import json
import logging
import ssl

import RPi.GPIO as GPIO
import websockets


class Gateway:

    def __init__(
        self,
        in_config,
        in_path,
        in_voiceRecorder,
        in_audioPlayer,
        in_mpdPlayer,
        in_volumeControl
    ):

        self.host = in_config["host"]
        self.port = in_config["port"]
        self.path = in_path

        self.voiceRecorder = in_voiceRecorder
        self.audioPlayer = in_audioPlayer
        self.mpdPlayer = in_mpdPlayer
        self.volumeControl = in_volumeControl

        self.samplerate = in_config[
            "samplerate_input"
        ]

        self.websocket = None

        self.task_listen_incoming = None
        self.task_listen_second_connection = None
        self.tasks_listen_recorder = []

        # ------------------------------------------------------
        # Ожидание ответа на команду.
        # ------------------------------------------------------

        self.command_pending = False
        self.command_blink_task = None

        # ------------------------------------------------------
        # SSL
        # ------------------------------------------------------

        self.ssl_context = (
            ssl.create_default_context()
        )

        self.ssl_context.check_hostname = False

        self.ssl_context.verify_mode = (
            ssl.CERT_NONE
        )

        # ------------------------------------------------------
        # Логирование
        # ------------------------------------------------------

        self._logger = logging.getLogger(
            "Gateway"
        )

        self._logger.setLevel(
            logging.DEBUG
        )

        if not self._logger.handlers:

            console_handler = (
                logging.StreamHandler()
            )

            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            )

            console_handler.setFormatter(
                formatter
            )

            self._logger.addHandler(
                console_handler
            )

        # ------------------------------------------------------
        # GPIO
        # ------------------------------------------------------

        GPIO.setmode(
            GPIO.BCM
        )

        self.LED_PIN = 13

        GPIO.setup(
            self.LED_PIN,
            GPIO.OUT
        )

        # LED ON = нет соединения с сервером.
        self.led_on = True

        GPIO.output(
            self.LED_PIN,
            GPIO.HIGH
        )

        self._logger.debug(
            "Светодиод включен"
        )

    # ==========================================================
    # Индикация ожидания ответа
    # ==========================================================

    def start_command_blink(self):

        self.command_pending = True

        if self.command_blink_task is None:

            self._logger.debug(
                "Начинаем мигание: "
                "ожидание ответа от сервера."
            )

            self.command_blink_task = (
                asyncio.create_task(
                    self._command_blink()
                )
            )

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

            GPIO.output(
                self.LED_PIN,
                GPIO.LOW
            )

            self._logger.debug(
                "Ответ получен. "
                "Мигание остановлено, "
                "светодиод выключен."
            )

    async def _command_blink(self):

        try:

            while self.command_pending:

                GPIO.output(
                    self.LED_PIN,
                    GPIO.HIGH
                )

                await asyncio.sleep(
                    0.5
                )

                if not self.command_pending:
                    break

                GPIO.output(
                    self.LED_PIN,
                    GPIO.LOW
                )

                await asyncio.sleep(
                    0.5
                )

        except asyncio.CancelledError:

            raise

    # ==========================================================
    # Подключение
    # ==========================================================

    async def connect(self):

        while True:

            try:

                self.websocket = (
                    await websockets.connect(
                        f"wss://{self.host}:"
                        f"{self.port}"
                        f"{self.path}",
                        ssl=self.ssl_context
                    )
                )

                self._logger.debug(
                    "Подключен к серверу!"
                )

                await self.send_message(
                    json.dumps({
                        "type":
                            "negotiate/request",

                        "protocols": [
                            [
                                "in.text-direct",
                                "in.text-indirect"
                            ],
                            [
                                "out.audio.link"
                            ],
                            [
                                "out.tts.serverside",
                                "out.text-plain"
                            ],
                            [
                                "in.stt.serverside",
                                "in.stt.clientside",
                                "in.text-indirect"
                            ],
                            [
                                "in.mute"
                            ],
                            [
                                "out.volume"
                            ]
                        ]
                    })
                )

                await self.wait_first_response()

                # --------------------------------------------------
                # Соединение установлено.
                # --------------------------------------------------

                self.command_pending = False

                if self.command_blink_task is not None:

                    await self.stop_command_blink()

                if self.led_on:

                    self._logger.debug(
                        "Светодиод выключен"
                    )

                    self.led_on = False

                    GPIO.output(
                        self.LED_PIN,
                        GPIO.LOW
                    )

                if self.task_listen_incoming is None:

                    self._logger.debug(
                        "Создаем задачу приема сообщений."
                    )

                    self.task_listen_incoming = (
                        asyncio.create_task(
                            self.listen_for_incoming_messages()
                        )
                    )

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

                GPIO.output(
                    self.LED_PIN,
                    GPIO.HIGH
                )

                self._logger.warning(
                    f"Сервер недоступен: {e}. "
                    f"Повторная попытка через 5 секунд..."
                )

                await asyncio.sleep(
                    5
                )

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

                GPIO.output(
                    self.LED_PIN,
                    GPIO.HIGH
                )

                self._logger.exception(
                    f"Ошибка соединения с сервером: {e}. "
                    f"Повторная попытка через 5 секунд..."
                )

                await asyncio.sleep(
                    5
                )

    # ==========================================================
    # Закрытие
    # ==========================================================

    async def close(self):

        self.command_pending = False

        if self.command_blink_task is not None:

            self.command_blink_task.cancel()

            try:
                await self.command_blink_task

            except asyncio.CancelledError:
                pass

            self.command_blink_task = None

        if self.websocket is not None:

            try:

                await self.websocket.close()

                self._logger.debug(
                    "Отключен от сервера."
                )

            except Exception as e:

                self._logger.debug(
                    f"Ошибка закрытия WebSocket: {e}"
                )

            finally:

                self.websocket = None

        self.led_on = True

        GPIO.output(
            self.LED_PIN,
            GPIO.HIGH
        )

    # ==========================================================
    # WebSocket
    # ==========================================================

    async def send_message(
            self,
            in_message
    ):

        self._logger.debug(
            f"send_message: {in_message}"
        )

        await self.websocket.send(
            in_message
        )

        self._logger.debug(
            f"отправил: {in_message}"
        )

    async def receive_message(self):

        try:

            return await self.websocket.recv()

        except websockets.ConnectionClosedError:

            self._logger.debug(
                "Соединение неожиданно прервано."
            )

            self.command_pending = False

            if self.command_blink_task is not None:

                self.command_blink_task.cancel()

                try:
                    await self.command_blink_task

                except asyncio.CancelledError:
                    pass

                self.command_blink_task = None

            self.led_on = True

            GPIO.output(
                self.LED_PIN,
                GPIO.HIGH
            )

            self._logger.debug(
                "Светодиод включен"
            )

            raise

    async def wait_first_response(self):

        first_response = (
            await self.receive_message()
        )

        if first_response is not None:

            self._logger.debug(
                f"Первый ответ: "
                f"{first_response}"
            )

            await self.send_message(
                json.dumps({
                    "type":
                        "in.text-direct/text",

                    "text":
                        "соединение установлено"
                })
            )

    # ==========================================================
    # Прием сообщений
    # ==========================================================

    async def listen_for_incoming_messages(
            self
    ):

        while True:

            try:

                response = (
                    await self.receive_message()
                )

                get_data = json.loads(
                    response
                )

                self._logger.debug(
                    f"ПОЛНОЕ ВХОДЯЩЕЕ СООБЩЕНИЕ: "
                    f"{get_data}"
                )

                if get_data.get("text") is not None:

                    self._logger.debug(
                        f"получено >>> text: "
                        f"{get_data.get('text')}"
                    )

                if get_data.get("altText") is not None:

                    self._logger.debug(
                        f"получено >>> altText: "
                        f"{get_data.get('altText')}"
                    )

                type_message = (
                    get_data.get("type")
                )

                if type_message is None:
                    continue

                # --------------------------------------------------
                # Сервер распознал голосовую команду.
                #
                # Саму команду здесь НЕ обрабатываем.
                #
                # Её обрабатывает серверный
                # plugin_volume_commands.py.
                #
                # Здесь только запускаем индикацию ожидания
                # голосового ответа.
                # --------------------------------------------------

                if type_message == (
                    "in.stt.serverside/processed"
                ):

                    text = get_data.get(
                        "text"
                    )

                    if text:

                        self._logger.debug(
                            f"Обработка голосовой команды "
                            f"сервером: {text}"
                        )

                        self.start_command_blink()

                # --------------------------------------------------
                # Mute
                # --------------------------------------------------

                if type_message == "in.mute/mute":

                    self.voiceRecorder.resume(
                        False
                    )

                # --------------------------------------------------
                # Unmute
                # --------------------------------------------------

                if type_message == "in.mute/unmute":

                    self.voiceRecorder.resume(
                        True
                    )

                # --------------------------------------------------
                # Команда изменения громкости от сервера.
                # --------------------------------------------------

                if type_message == (
                    "out.volume/command"
                ):

                    self._logger.info(
                        f"VOLUME RX: "
                        f"typeMessage="
                        f"{type_message!r}, "
                        f"get_data="
                        f"{get_data!r}"
                    )

                    self.start_command_blink()

                    asyncio.create_task(
                        self.handle_volume_command(
                            get_data
                        )
                    )

                # --------------------------------------------------
                # Готовность дополнительного соединения STT.
                # --------------------------------------------------

                if type_message == (
                    "in.stt.serverside/ready"
                ):

                    self.task_listen_second_connection = (
                        asyncio.create_task(
                            self.handle_connection(
                                get_data.get("path"),
                                self.samplerate
                            )
                        )
                    )

                # --------------------------------------------------
                # Ответ сервера в виде аудио.
                # --------------------------------------------------

                if (
                    "out.audio.link/playback-request"
                    in type_message
                ):

                    asyncio.create_task(
                        self.play_response_audio(
                            get_data
                        )
                    )

            except websockets.ConnectionClosedError:

                self._logger.debug(
                    "Соединение потеряно. "
                    "Повторное подключение..."
                )

                self.command_pending = False

                if self.command_blink_task is not None:

                    self.command_blink_task.cancel()

                    try:
                        await self.command_blink_task

                    except asyncio.CancelledError:
                        pass

                    self.command_blink_task = None

                self.led_on = True

                GPIO.output(
                    self.LED_PIN,
                    GPIO.HIGH
                )

                self._logger.debug(
                    "Светодиод включен"
                )

                self.voiceRecorder.resume(
                    False
                )

                for task in (
                    self.tasks_listen_recorder
                ):

                    task.cancel()

                self.tasks_listen_recorder.clear()

                await self.reconnect()

    # ==========================================================
    # Воспроизведение ответа
    # ==========================================================

    async def play_response_audio(
            self,
            data
    ):

        try:

            await asyncio.to_thread(
                self.audioPlayer.play,
                self,
                data.get("playbackId"),
                data.get("url"),
                self.mpdPlayer
            )

        except Exception as e:

            self._logger.exception(
                f"Ошибка воспроизведения ответа: {e}"
            )

        finally:

            # Голосовой ответ закончен.
            await self.stop_command_blink()

    # ==========================================================
    # Переподключение
    # ==========================================================

    async def reconnect(self):

        if self.task_listen_second_connection is not None:

            self._logger.debug(
                "Удаляем старое "
                "second_connection."
            )

            self.task_listen_second_connection.cancel()

            self.task_listen_second_connection = None

        while True:

            try:

                await self.connect()

                break

            except Exception as e:

                self._logger.exception(
                    f"Повторное подключение "
                    f"не удалось: {e}. "
                    f"Повторная попытка..."
                )

                await asyncio.sleep(
                    5
                )

    # ==========================================================
    # Дополнительное соединение для записи
    # ==========================================================

    async def handle_connection(
        self,
        in_path,
        in_sample_rate
    ):

        async with websockets.connect(
            f"wss://{self.host}:{self.port}"
            f"{in_path}"
            f"?sample_rate={in_sample_rate}",
            ssl=self.ssl_context
        ) as websocket:

            self._logger.debug(
                "Дополнительное соединение!"
            )

            tasks = [
                asyncio.create_task(
                    self.voiceRecorder.producer()
                ),
                asyncio.create_task(
                    self.voiceRecorder.consumer(
                        websocket
                    )
                )
            ]

            self.tasks_listen_recorder.extend(
                tasks
            )

            await asyncio.gather(
                *tasks
            )

    # ==========================================================
    # Отправка текста серверу для озвучивания
    # ==========================================================

    async def send_text_for_speech(
            self,
            text
    ):

        if self.websocket is None:

            self._logger.warning(
                "Невозможно отправить текст: "
                "WebSocket не подключен."
            )

            return False

        try:

            message = {
                "type":
                    "in.text-direct/text",

                "text":
                    text
            }

            self._logger.debug(
                f"Отправляем текст "
                f"для озвучивания: "
                f"{text!r}"
            )

            await self.send_message(
                json.dumps(message)
            )

            return True

        except Exception as e:

            self._logger.exception(
                "Ошибка отправки текста "
                f"для озвучивания: {e}"
            )

            return False

    # ==========================================================
    # Обработка out.volume/command
    # ==========================================================

    async def handle_volume_command(
            self,
            data
    ):

        command_id = data.get(
            "commandId"
        )

        command = data.get(
            "command"
        )

        value = data.get(
            "value"
        )

        self._logger.debug(
            f"Обработка out.volume: "
            f"commandId={command_id}, "
            f"command={command}, "
            f"value={value}"
        )

        result = {
            "commandId": command_id,
            "success": False
        }

        if self.volumeControl is None:

            self._logger.warning(
                "VolumeControl не подключен."
            )

            await self.send_message(
                json.dumps({
                    "type":
                        "out.volume/result",

                    **result
                })
            )

            await self.stop_command_blink()

            return

        try:

            # --------------------------------------------------
            # Увеличение громкости.
            # --------------------------------------------------

            if command == "up":

                success = (
                    self.volumeControl.volume_up()
                )

            # --------------------------------------------------
            # Уменьшение громкости.
            # --------------------------------------------------

            elif command == "down":

                success = (
                    self.volumeControl.volume_down()
                )

            # --------------------------------------------------
            # Установка абсолютного значения.
            #
            # Значение трактуется как пользовательские
            # проценты 0..100.
            # --------------------------------------------------

            elif command == "set":

                success = (
                    self.volumeControl.set_volume_percent(
                        value
                    )
                )

            # --------------------------------------------------
            # Получение текущей громкости.
            #
            # Возвращаем пользовательский уровень 0..100%.
            # --------------------------------------------------

            elif command == "get":

                current_volume = (
                    self.volumeControl.get_volume_percent()
                )

                if current_volume is None:

                    success = False

                else:

                    success = True

                    result["volume"] = (
                        current_volume
                    )

            # --------------------------------------------------
            # Минимальная громкость.
            # --------------------------------------------------

            elif command == "min":

                success = (
                    self.volumeControl.volume_min()
                )

            # --------------------------------------------------
            # Средняя громкость.
            # --------------------------------------------------

            elif command == "middle":

                success = (
                    self.volumeControl.volume_middle()
                )

            # --------------------------------------------------
            # Максимальная громкость.
            # --------------------------------------------------

            elif command == "max":

                success = (
                    self.volumeControl.volume_max()
                )

            # --------------------------------------------------
            # Физический mute.
            # --------------------------------------------------

            elif command == "mute":

                success = (
                    self.volumeControl.volume_mute()
                )

            # --------------------------------------------------
            # Возврат к средней громкости.
            # --------------------------------------------------

            elif command == "unmute":

                success = (
                    self.volumeControl.volume_unmute()
                )

            else:

                self._logger.warning(
                    f"Неизвестная команда громкости: "
                    f"{command}"
                )

                success = False

            self._logger.debug(
                f"Результат volumeControl: "
                f"success={success!r}, "
                f"type={type(success).__name__}"
            )

            result["success"] = bool(
                success
            )

            # --------------------------------------------------
            # Для команд изменения громкости возвращаем
            # актуальное значение.
            #
            # Для "get" оно уже получено выше.
            # --------------------------------------------------

            if (
                success
                and command != "get"
            ):

                current_volume = (
                    self.volumeControl.get_volume_percent()
                )

                if current_volume is not None:

                    result["volume"] = (
                        current_volume
                    )

            response = {
                "type":
                    "out.volume/result",

                **result
            }

            self._logger.debug(
                f"ОТПРАВЛЯЕМ РЕЗУЛЬТАТ VOLUME: "
                f"{response}"
            )

            await self.send_message(
                json.dumps(response)
            )

            self._logger.debug(
                f"РЕЗУЛЬТАТ VOLUME ОТПРАВЛЕН: "
                f"commandId={command_id}"
            )

        except Exception as e:

            self._logger.exception(
                f"Ошибка обработки "
                f"команды громкости: {e}"
            )

            result["success"] = False

            response = {
                "type":
                    "out.volume/result",

                **result
            }

            self._logger.debug(
                f"ОТПРАВЛЯЕМ ОШИБКУ VOLUME: "
                f"{response}"
            )

            await self.send_message(
                json.dumps(response)
            )

        finally:

            await self.stop_command_blink()
