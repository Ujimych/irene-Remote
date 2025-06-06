import asyncio
import sounddevice
from queue import Queue
import logging

class Recorder:
    def __init__(self, in_config):
        """Инициализация основных атрибутов экземпляра класса"""
        self.audio_queue = Queue(maxsize=in_config["buffersize_input"])       # Размер очереди
        self.recording_flag = False                                            # Флаг состояния записи
        self.input_stream = None                                               # Поток ввода звука
        self.config = {
            'device': in_config["device_input"],                 # Устройство захвата звука
            'blocksize': in_config["blocksize_input"],           # Размер блока
            'dtype': in_config["dtype_input"],                   # Тип данных
            'samplerate': in_config["samplerate_input"],         # Частота дискретизации
            'channels': in_config["channels_input"]              # Количество каналов (моно)
        }

        self._logger = logging.getLogger('Recorder')
        self._logger.setLevel(logging.DEBUG)

        # Добавляем обработчик для вывода в консоль
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

    def capture_callback(self, indata, frames, time, status):
        """Производит захват аудиоданных и кладёт их в очередь."""
        if not self.recording_flag or status:
            return
        
        # Преобразуем массив NumPy в байтовое представление
        audio_bytes = bytes(indata)
        # Добавляем в очередь
        self.audio_queue.put_nowait(audio_bytes)
    
    async def producer(self):
        """Запускает процесс записи аудиоданных и управляет потоком записи."""
        self._logger.debug("Начинаем захват аудиоданных и помещаем их в очередь.")
        try:
            # Устанавливаем флаг начала записи
            self.recording_flag = True
            self._logger.debug("Начало записи...")
            
            # Если ранее поток уже существовал, мы можем сразу начать записывать,
            # иначе создадим новый поток
            if self.input_stream is None:
                # Создаем входящий аудиопоток
                self.input_stream = sounddevice.RawInputStream(
                    device=self.config['device'],           # устройство захвата звука
                    samplerate=self.config['samplerate'],   # частота дискретизации
                    blocksize=self.config['blocksize'],     # размер блока
                    dtype=self.config['dtype'],             # тип данных
                    channels=self.config['channels'],       # количество каналов
                    callback=self.capture_callback          # обратный вызов для обработки данных
                )
                
            # Начинаем слушание звукового устройства
            with self.input_stream:
                while self.recording_flag:
                    await asyncio.sleep(0.1)  # короткая пауза для предотвращения блокировок
        except Exception as e:
            self._logger.exception(f"Запись прервана из-за ошибки: {e}")
        finally:
            self._logger.debug("Завершаем работу потока")
            # Завершаем работу потока
            if self.input_stream is not None and self.input_stream.active:
                self.input_stream.stop()
                self.input_stream.close()

    async def consumer(self, in_websocket):
        """Потребляет данные из очереди и отправляет их через вебсокет."""
        while True:
            if self.audio_queue.empty():
                await asyncio.sleep(0.1)  # ждем появления новых данных
                continue
            
            # Забираем данные из очереди
            data = await asyncio.to_thread(self.audio_queue.get)
            try:
                # Отправляем данные через вебсокет
                await in_websocket.send(data)
            except Exception as e:
                pass
                self._logger.exception(f'Ошибка отправки данных: {e}')

    def resume(self, in_paused):
        """Приостанавливает или возобновляет запись."""
        self.recording_flag = in_paused
        if not self.recording_flag:
            self._logger.debug("Запись приостановлена.")
            # Останавливаем и освобождаем поток
            if self.input_stream is not None and self.input_stream.active:
                self.input_stream.stop()
                self.input_stream.close()
                self.input_stream = None  # очищаем ссылку на объект
        else:
            self._logger.debug("Запись возобновлена.")
            # Перезапускаем поток
            if self.input_stream is None:
                self.input_stream = sounddevice.RawInputStream(
                    device=self.config['device'],           # устройство захвата звука
                    samplerate=self.config['samplerate'],   # частота дискретизации
                    blocksize=self.config['blocksize'],     # размер блока
                    dtype=self.config['dtype'],             # тип данных
                    channels=self.config['channels'],       # количество каналов
                    callback=self.capture_callback          # обратный вызов для обработки данных
                )
                self.input_stream.start()  # запускаем поток снова

