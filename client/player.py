import logging
import os
import subprocess
import tempfile
import urllib.request

import soundfile

class Player:

    def __init__(self, in_config):
        self.host = in_config["host"]
        self.port = in_config["port"]
        self.alsa_device = "plughw:CARD=seeed2micvoicec,DEV=0"
        self._logger = logging.getLogger("Player")
        self._logger.setLevel(logging.DEBUG)

        if not self._logger.handlers:
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

    def play(self, in_gateway, in_playback_id, in_path, in_mpdPlayer):
        self._logger.debug(f"play >>> playback_id: {in_playback_id}")
        cache_file = None
        mpd_was_playing = False
        listen_mode = False

        try:
            listen_mode = bool(getattr(in_gateway, "listen_mode", False))
            self._logger.debug(f"Режим 'Слушай' перед воспроизведением: {listen_mode}")

            cache_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            audio_url = f"https://{self.host}:{self.port}{in_path}"
            self._logger.debug(f"Загрузка аудио: {audio_url}")

            audio_data = urllib.request.urlopen(audio_url, context=in_gateway.ssl_context).read()
            with open(cache_file, "wb") as output:
                output.write(audio_data)
            self._logger.debug(f"Получено аудио: {len(audio_data)} байт")

            with soundfile.SoundFile(cache_file) as audio_file:
                source_samplerate = audio_file.samplerate
                source_channels = audio_file.channels
                source_subtype = audio_file.subtype
                duration = len(audio_file) / source_samplerate

                self._logger.debug(f"WAV: {source_samplerate} Гц, {source_channels} канал(а), {source_subtype}, длительность: {duration:.2f} сек.")

                if not listen_mode and in_mpdPlayer is not None:
                    mpd_was_playing = in_mpdPlayer.pause_for_voice()
                    self._logger.debug(f"MPD перед обычным голосовым ответом играл: {mpd_was_playing}")
                elif listen_mode:
                    self._logger.debug("Режим 'Слушай' активен. Повторная остановка MPD не требуется.")

                self._logger.debug(f"Воспроизведение через ALSA: {self.alsa_device}")
                result = subprocess.run(["aplay", "-D", self.alsa_device, cache_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if result.returncode != 0:
                    self._logger.error(f"aplay завершился с ошибкой: код={result.returncode}")
                    if result.stderr:
                        self._logger.error(f"aplay stderr: {result.stderr.strip()}")
                    raise RuntimeError("Ошибка воспроизведения через ALSA aplay")

                self._logger.debug("Аудиоустройство успешно воспроизвело WAV.")
            self._logger.debug("Воспроизведение закончено.")

        except Exception as e:
            self._logger.exception(f"Возникла ошибка воспроизведения: {e}")

        finally:
            if mpd_was_playing and in_mpdPlayer is not None and not listen_mode:
                self._logger.debug("Восстанавливаем MPD после обычного голосового ответа.")
                try:
                    in_mpdPlayer.resume_after_voice()
                except Exception as e:
                    self._logger.exception(f"Ошибка восстановления MPD: {e}")

            if cache_file is not None:
                try:
                    os.remove(cache_file)
                    self._logger.debug("Временный WAV удалён.")
                except OSError as e:
                    self._logger.debug(f"Не удалось удалить временный WAV: {e}")
