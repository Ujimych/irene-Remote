import asyncio
import logging
from queue import Queue

import sounddevice


class Recorder:

    def __init__(self, in_config):
        self.audio_queue = Queue(
            maxsize=in_config["buffersize_input"]
        )

        self.recording_flag = False
        self.input_stream = None

        self.config = {
            "device": in_config["device_input"],
            "blocksize": in_config["blocksize_input"],
            "dtype": in_config["dtype_input"],
            "samplerate": in_config["samplerate_input"],
            "channels": in_config["channels_input"]
        }

        self._logger = logging.getLogger("Recorder")
        self._logger.setLevel(logging.DEBUG)

        if not self._logger.handlers:
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

    def capture_callback(
        self,
        indata,
        frames,
        time,
        status
    ):
        """Получить аудиоданные и поместить их в очередь."""
        if not self.recording_flag or status:
            return

        audio_bytes = bytes(indata)

        try:
            self.audio_queue.put_nowait(audio_bytes)
        except Exception:
            pass

    def _create_input_stream(self):
        return sounddevice.RawInputStream(
            device=self.config["device"],
            samplerate=self.config["samplerate"],
            blocksize=self.config["blocksize"],
            dtype=self.config["dtype"],
            channels=self.config["channels"],
            callback=self.capture_callback
        )

    async def producer(self):
        """Запустить захват аудио."""
        self._logger.debug(
            "Начинаем захват аудиоданных."
        )

        try:
            self.recording_flag = True
            self._logger.debug("Начало записи...")

            if self.input_stream is None:
                self.input_stream = self._create_input_stream()

            with self.input_stream:
                while self.recording_flag:
                    await asyncio.sleep(0.1)

        except Exception as e:
            self._logger.exception(
                f"Запись прервана из-за ошибки: {e}"
            )

        finally:
            self._logger.debug(
                "Завершаем работу потока"
            )

            if (
                self.input_stream is not None
                and self.input_stream.active
            ):
                self.input_stream.stop()
                self.input_stream.close()

    async def consumer(self, in_websocket):
        """Отправлять аудиоданные через WebSocket."""
        while True:
            if self.audio_queue.empty():
                await asyncio.sleep(0.1)
                continue

            data = await asyncio.to_thread(
                self.audio_queue.get
            )

            try:
                await in_websocket.send(data)

            except Exception as e:
                self._logger.error(
                    f"Ошибка отправки данных: {e}"
                )

    def resume(self, in_paused):
        """Приостановить или возобновить запись."""
        self.recording_flag = in_paused

        if not self.recording_flag:
            self._logger.debug(
                "Запись приостановлена."
            )

            if (
                self.input_stream is not None
                and self.input_stream.active
            ):
                self.input_stream.stop()
                self.input_stream.close()
                self.input_stream = None

            return

        self._logger.debug(
            "Запись возобновлена."
        )

        if self.input_stream is None:
            self.input_stream = self._create_input_stream()
            self.input_stream.start()
