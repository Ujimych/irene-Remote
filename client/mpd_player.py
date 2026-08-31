import logging
import threading

import mpd

class MpdPlayer:

    def __init__(self, host="localhost", port=6600, volume_step=10):
        self.host = host
        self.port = port
        self.volume_step = volume_step
        self.client = None
        self.was_playing = False
        self.listen_was_playing = False
        self._lock = threading.Lock()
        self._logger = logging.getLogger("MpdPlayer")
        self._logger.setLevel(logging.DEBUG)

        if not self._logger.handlers:
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        self._connect()

    def _connect(self):
        try:
            client = mpd.MPDClient()
            client.connect(self.host, self.port)
            self.client = client
            self._logger.info(f"Подключение к MPD выполнено: {self.host}:{self.port}")
        except Exception as e:
            self.client = None
            self._logger.error(f"Подключение к MPD невозможно: {e}")

    def _ensure_connection(self):
        if self.client is not None:
            try:
                self.client.ping()
                return True
            except Exception:
                self._logger.warning("Соединение с MPD потеряно. Выполняем переподключение.")
                self.client = None
        self._connect()
        return self.client is not None

    def pause_for_voice(self):
        with self._lock:
            if not self._ensure_connection():
                self.was_playing = False
                return False
            try:
                status = self.client.status()
                state = status.get("state")
                self._logger.debug(f"MPD состояние перед голосом: {state}")
                if state == "play":
                    self.was_playing = True
                    self.client.stop()
                    self._logger.info("MPD остановлен для воспроизведения голосового ответа.")
                    return True
                self.was_playing = False
                return False
            except Exception as e:
                self._logger.exception(f"Ошибка остановки MPD: {e}")
                self.client = None
                self.was_playing = False
                return False

    def resume_after_voice(self):
        with self._lock:
            if not self.was_playing:
                self._logger.debug("MPD до голосового ответа не воспроизводился. Возобновление не требуется.")
                return False
            if not self._ensure_connection():
                self.was_playing = False
                return False
            try:
                self.client.play()
                self._logger.info("MPD возобновлён после голосового ответа.")
                self.was_playing = False
                return True
            except Exception as e:
                self._logger.exception(f"Ошибка возобновления MPD: {e}")
                self.client = None
                self.was_playing = False
                return False

    def start_listen_mode(self):
        with self._lock:
            # На всякий случай сбрасываем старое состояние.
            self.listen_was_playing = False
            if not self._ensure_connection():
                self._logger.warning("Невозможно проверить состояние MPD перед режимом 'Слушай'.")
                return False
            try:
                status = self.client.status()
                state = status.get("state")
                self._logger.debug(f"MPD состояние перед режимом 'Слушай': {state}")
                if state == "play":
                    self.listen_was_playing = True
                    self.client.stop()
                    self._logger.info("MPD остановлен для режима 'Слушай'.")
                    return True
                self._logger.debug("MPD перед режимом 'Слушай' не воспроизводился.")
                return False
            except Exception as e:
                self._logger.exception(f"Ошибка подготовки MPD к режиму 'Слушай': {e}")
                self.client = None
                self.listen_was_playing = False
                return False

    def finish_listen_mode(self):
        with self._lock:
            if not self.listen_was_playing:
                self._logger.debug("До режима 'Слушай' MPD не воспроизводился. Возобновление не требуется.")
                return False
            if not self._ensure_connection():
                self.listen_was_playing = False
                return False
            try:
                self.client.play()
                self._logger.info("MPD возобновлён после режима 'Слушай'.")
                self.listen_was_playing = False
                return True
            except Exception as e:
                self._logger.exception(f"Ошибка возобновления MPD после режима 'Слушай': {e}")
                self.client = None
                self.listen_was_playing = False
                return False

    def cancel_listen_mode(self):
        with self._lock:
            self.listen_was_playing = False
            self._logger.debug("Состояние режима 'Слушай' сброшено без восстановления MPD.")

    def play(self):
        with self._lock:
            if not self._ensure_connection(): return False
            try:
                self.client.play()
                self._logger.info("MPD: воспроизведение запущено.")
                return True
            except Exception as e:
                self._logger.exception(f"Ошибка запуска MPD: {e}")
                self.client = None
                return False

    def stop(self):
        with self._lock:
            if not self._ensure_connection(): return False
            try:
                self.client.stop()
                self.was_playing = False
                self.listen_was_playing = False
                self._logger.info("MPD: воспроизведение остановлено.")
                return True
            except Exception as e:
                self._logger.exception(f"Ошибка остановки MPD: {e}")
                self.client = None
                return False

    def get_volume(self):
        with self._lock:
            if not self._ensure_connection(): return None
            try:
                status = self.client.status()
                volume = int(status.get("volume", 0))
                self._logger.debug(f"MPD громкость: {volume}")
                return volume
            except Exception as e:
                self._logger.exception(f"Ошибка получения громкости MPD: {e}")
                self.client = None
                return None

    def set_volume(self, volume):
        with self._lock:
            if not self._ensure_connection(): return False
            try:
                volume = max(0, min(100, int(volume)))
                self.client.setvol(volume)
                self._logger.info(f"MPD громкость установлена: {volume}")
                return True
            except Exception as e:
                self._logger.exception(f"Ошибка установки громкости MPD: {e}")
                self.client = None
                return False

    def volume_up(self):
        current_volume = self.get_volume()
        if current_volume is None: return False
        new_volume = min(100, current_volume + self.volume_step)
        return self.set_volume(new_volume)

    def volume_down(self):
        current_volume = self.get_volume()
        if current_volume is None: return False
        new_volume = max(0, current_volume - self.volume_step)
        return self.set_volume(new_volume)

    def close(self):
        with self._lock:
            if self.client is None: return
            try: self.client.close()
            except Exception: pass
            try: self.client.disconnect()
            except Exception: pass
            self.client = None; self.was_playing = False; self.listen_was_playing = False; self._logger.debug("Соединение с MPD закрыто.")

