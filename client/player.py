import sounddevice
import soundfile
import urllib.request
import tempfile
import logging

class Player:
    def __init__(self, in_config):
        self.config = {
            'protocol': 'https://',
            'host': in_config["host"],
            'port': in_config["port"],
            'device': in_config["device_output"],              # Устройство воспроизведения
            'blocksize': in_config["blocksize_output"],        # Размер блока
            'dtype': in_config["dtype_output"],                # Тип данных
            'samplerate': in_config["samplerate_output"],      # Частота дискретизации
            'channels': in_config["channels_output"]           # Количество каналов (моно)
        }

        self._logger = logging.getLogger('Player')
        self._logger.setLevel(logging.DEBUG)

        # Добавляем обработчик для вывода в консоль
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

    def play(self, in_gateway, in_playback_id, in_path):
        self._logger.debug(f"play >>> playback_id: {in_playback_id}")

        if self.config['device'] == "":
            self._logger.exception("Устройство захвата звука НЕ задано!")

        cache_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
        audio_url = f"{self.config['protocol']}{self.config['host']}:{self.config['port']}{in_path}"
        audio_data = urllib.request.urlopen(audio_url, context=in_gateway.ssl_context).read()
        with open(cache_file, 'wb') as output:
            output.write(audio_data)

        try:
            with soundfile.SoundFile(cache_file) as f:
                self._logger.debug(f'Частота [Гц]: {f.samplerate}, Длительность: {round(len(f)/f.samplerate)} сек.')
                block_size = self.config['blocksize']
                num_channels = f.channels
                dtype = self.config['dtype']

                # Прямая загрузка аудиофайлов и воспроизведение через RawOutputStream
                with sounddevice.RawOutputStream(
                    samplerate=f.samplerate,
                    blocksize=block_size,
                    device=self.config['device'],
                    channels=num_channels,
                    dtype=self.config['dtype']
                ) as stream:
                    while True:
                        # Чтение данных из файла блоками
                        data = f.buffer_read(block_size, dtype)
                        if not data:
                            break
                        # Непосредственно выводим данные
                        stream.write(data)
                        
            self._logger.debug("Воспроизведение закончено.")

        except Exception as e:
            self._logger.exception(f"Возникла ошибка воспроизведения: {e}")
        finally:
            # Удаляем временный файл
            try:
                import os
                os.remove(cache_file)
            except OSError:
                pass