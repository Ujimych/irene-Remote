import ssl
import json
import asyncio
import websockets
import RPi.GPIO as GPIO
import logging

class Gateway:

    def __init__(self, in_config, in_path, in_voiceRecorder, in_audioPlayer):
        self.host = in_config["host"]
        self.port = in_config["port"]
        self.path = in_path
        self.voiceRecorder = in_voiceRecorder
        self.audioPlayer = in_audioPlayer
        self.samplerate = in_config["samplerate_input"]
        self.websocket = None
        self.is_connected_and_answered = False  # Флаг готовности постоянного подключения

        self.task_listen_incoming = None                 # Фоновый процесс приема входящих сообщений
        self.task_listen_second_connection = None        # Задача для вторичного соединения

        self.tasks_listen_recorder = []

        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

        self.stop_event = asyncio.Event()

        self._logger = logging.getLogger('Gateway')
        self._logger.setLevel(logging.DEBUG)

        # Добавляем обработчик для вывода в консоль
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # Используем нумерацию контактов BCM
        GPIO.setmode(GPIO.BCM)

        # Назначаем контакт 13 на выход
        self.LED_PIN = 13
        GPIO.setup(self.LED_PIN, GPIO.OUT)

        # Включаем светодиод
        self._logger.debug("Светодиод включен")
        self.led_on = True
        GPIO.output(self.LED_PIN, GPIO.HIGH)

    async def connect(self):
        while True:
            try:
                self.websocket = await websockets.connect(f'wss://{self.host}:{self.port}{self.path}', ssl=self.ssl_context)
                self._logger.debug("Подключен к серверу!")

                # Отправка первого запроса
                await self.send_message(json.dumps({
                    "type": "negotiate/request",
                    "protocols": [
                        ["in.text-direct", "in.text-indirect"],
                        ["out.audio.link"],
                        ["out.tts.serverside", "out.text-plain"],
                        ["in.stt.serverside", "in.stt.clientside", "in.text-indirect"],
                        ["in.mute"]
                    ]
                }))

                await self.wait_first_response()  # Ожидаем ответа от сервера

                if self.led_on == True:
                    self._logger.debug("Светодиод выключен")
                    self.led_on = False
                    GPIO.output(self.LED_PIN, GPIO.LOW)

                # Запускаем циклы постоянных процессов только после первого успешного ответа
                if self.task_listen_incoming is None:
                    self._logger.debug("### Создаем _incoming.")
                    self.task_listen_incoming = asyncio.create_task(self.listen_for_incoming_messages())

                break
            except Exception as e:
                self._logger.exception(f"Соединение не удалось: {e}. Повторная попытка...")
                await asyncio.sleep(5)  # Повторяем попытку через 5 секунд

    async def close(self):
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
            self._logger.debug("Отключен от сервера.")

            if self.led_on == False:
                # Включаем светодиод
                self._logger.debug("Светодиод включен")
                self.led_on = True
                GPIO.output(self.LED_PIN, GPIO.HIGH)

    async def send_message(self, in_message):
        self._logger.debug(f"send_message: {in_message}")

        await self.websocket.send(in_message)
        self._logger.debug(f"отправил: {in_message}")

    async def receive_message(self):
        try:
            response = await self.websocket.recv()
            # self._logger.debug(f"получено: {response}")
            return response
        except websockets.ConnectionClosedError:
            self._logger.debug("Соединение неожиданно прервано.")

            if self.led_on == False:
                # Включаем светодиод
                self._logger.debug("Светодиод включен")
                self.led_on = True
                GPIO.output(self.LED_PIN, GPIO.HIGH)

            raise

    async def wait_first_response(self):
        """Ждем прихода первого ответа перед началом постоянного цикла обработки запросов."""
        first_response = await self.receive_message()
        if first_response is not None:
            self.is_connected_and_answered = True
            self._logger.debug(f"первый ответ: {first_response}")

            await self.send_message( json.dumps( {"type":"in.text-direct/text","text":"соединение установлено"} ) )
    
    async def listen_for_incoming_messages(self):
        """Постоянное слушание входящих сообщений после получения первого ответа."""
        while True:
            try:
                # Обрабатываем входящее сообщение здесь
                response = await self.receive_message()
                # self._logger.debug( f'получено: {response}' )
                get_data = json.loads(response)
                if ( get_data.get('text') != None ):
                    self._logger.debug( f'получено >>> text: {get_data.get("text")}' )
                
                if ( get_data.get('altText') != None ):
                    self._logger.debug( f'получено >>> altText: {get_data.get("altText")}' )

                if ( get_data.get('type') != None ):
                    typeMessage = get_data.get('type')
                    
                    if ( typeMessage == "in.mute/mute" ):
                        # Перед началом воспроизведения звука останавливаем захват
                        # self._logger.debug( "receive «in.mute/mute»" )
                        self.voiceRecorder.resume( False )

                    if ( typeMessage == "in.mute/unmute" ):
                        # После завершения воспроизведения восстанавливаем захват
                        # self._logger.debug( "receive «in.mute/unmute»" )
                        self.voiceRecorder.resume( True )

                    if ( typeMessage == "in.stt.serverside/ready" ):
                        # self._logger.debug( "receive «in.stt.serverside/ready» >>> path: " + get_data.get('path') )
                        self.task_listen_second_connection = asyncio.create_task( self.handle_connection( get_data.get('path'), self.samplerate ) )

                    # if ( typeMessage == "in.stt.serverside/recognized" ):
                    #     self._logger.debug( "receive «in.stt.serverside/recognized» >>> text: " + get_data.get('text') )

                    # if ( typeMessage == "in.stt.serverside/processed" ):
                    #     self._logger.debug( "receive «in.stt.serverside/processed» >>> text: " + get_data.get('text') )

                    if ( typeMessage.find( "out.audio.link/playback-request" ) != -1 ):
                        self.audioPlayer.play( self, get_data.get('playbackId'), get_data.get('url') )

            except websockets.ConnectionClosedError:
                self._logger.debug("Соединение потеряно. Повторное подключение...")

                if self.led_on == False:
                    # Включаем светодиод
                    self._logger.debug("Светодиод включен")
                    self.led_on = True
                    GPIO.output(self.LED_PIN, GPIO.HIGH)

                self.voiceRecorder.resume( False )

                for task in self.tasks_listen_recorder:
                    task.cancel()
                self.tasks_listen_recorder.clear()  # очищаем список задач

                await self.reconnect()  # Инициируем повторное подключение
                continue  # Возвращаемся обратно в цикл прослушивания сообщений

    async def reconnect(self):

        if self.task_listen_second_connection is not None:
            self._logger.debug("### Удаляем старого second_connection.")
            self.task_listen_second_connection.cancel()
            self.task_listen_second_connection = None

        """Метод для повторного подключения к серверу после отключения."""
        while True:
            try:
                await self.connect()  # Пытаемся подключиться заново
                break
            except Exception as e:
                self._logger.exception(f"Повторное подключение не удалось: {e}. Повторная попытка...")
                await asyncio.sleep(5)  # Повторяем попытку через 5 секунд

    async def handle_connection(self, in_path, in_sample_rate):
        """Обработчик подключения к серверу"""
        async with websockets.connect( f'wss://{self.host}:{self.port}{in_path}?sample_rate={in_sample_rate}', ssl=self.ssl_context ) as websocket:
            self._logger.debug("Дополнительное соединение!")
            # Создаем две задачи: одна пишет в очередь, вторая читает из нее и отправляет
            tasks = [
                asyncio.create_task(self.voiceRecorder.producer()),
                asyncio.create_task(self.voiceRecorder.consumer(websocket))
            ]

            self.tasks_listen_recorder.extend(tasks)  # Сохраняем новые активные задачи
            await asyncio.gather(*tasks)  # Запускаем и ждём завершение всех задач

