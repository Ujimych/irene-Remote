import logging
import subprocess

class VolumeControl:

    def __init__(self, in_config):
        self.volume_step = int(in_config["volume_step"])
        self.mixer_card = str(in_config["mixer"]["card"])
        self.mixer_control = str(in_config["mixer"]["control"])

        self.min_volume = int(in_config["volume"]["min"])
        self.user_min_volume = int(in_config["volume"]["user_min"])
        self.middle_volume = int(in_config["volume"]["middle"])
        self.max_volume = int(in_config["volume"]["max"])

        if not (self.min_volume <= self.user_min_volume <= self.middle_volume <= self.max_volume):
            raise ValueError("Некорректная конфигурация громкости: должно выполняться min <= user_min <= middle <= max.")

        if self.volume_step <= 0:
            raise ValueError("volume_step должен быть больше 0.")

        self._logger = logging.getLogger("VolumeControl")
        self._logger.setLevel(logging.DEBUG)

        if not self._logger.handlers:
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        self.set_volume(self.middle_volume)

    def get_volume(self):
        try:
            result = subprocess.run(["amixer", "-c", self.mixer_card, "get", self.mixer_control], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            for line in result.stdout.splitlines():
                if "Front Left:" in line:
                    value = line.split("Playback")[1].split("[")[0].strip()
                    volume = int(value)
                    self._logger.debug(f"Текущая аппаратная громкость: {volume}")
                    return volume
            raise RuntimeError("Не удалось определить текущую громкость.")
        except Exception as e:
            self._logger.exception(f"Ошибка получения громкости: {e}")
            return None

    def set_volume(self, volume):
        try:
            volume = max(self.min_volume, min(self.max_volume, int(volume)))
            subprocess.run(["amixer", "-c", self.mixer_card, "set", self.mixer_control, str(volume)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            self._logger.info(f"Громкость установлена: {volume}")
            return True
        except Exception as e:
            self._logger.exception(f"Ошибка установки громкости: {e}")
            return False

    def volume_to_percent(self, volume):
        try:
            volume = int(volume)
            if volume <= self.user_min_volume: return 0
            if volume >= self.max_volume: return 100
            percent = round(((volume - self.user_min_volume) / (self.max_volume - self.user_min_volume)) * 100)
            return max(0, min(100, percent))
        except (TypeError, ValueError):
            self._logger.exception(f"Ошибка преобразования громкости в проценты: {volume}")
            return None

    def percent_to_volume(self, percent):
        try:
            percent = max(0, min(100, int(percent)))
            volume = round(self.user_min_volume + ((self.max_volume - self.user_min_volume) * percent / 100))
            return max(self.user_min_volume, min(self.max_volume, volume))
        except (TypeError, ValueError):
            self._logger.exception(f"Ошибка преобразования процентов в громкость: {percent}")
            return None

    def get_volume_percent(self):
        volume = self.get_volume()
        if volume is None: return None
        percent = self.volume_to_percent(volume)
        self._logger.debug(f"Пользовательская громкость: {percent}%")
        return percent

    def set_volume_percent(self, percent):
        volume = self.percent_to_volume(percent)
        if volume is None: return False
        self._logger.info(f"Установка громкости: {percent}% -> {volume}")
        return self.set_volume(volume)

    def volume_up(self):
        current_volume = self.get_volume()
        if current_volume is None: return False
        new_volume = min(self.max_volume, current_volume + self.volume_step)
        return self.set_volume(new_volume)

    def volume_down(self):
        current_volume = self.get_volume()
        if current_volume is None: return False
        new_volume = max(self.user_min_volume, current_volume - self.volume_step)
        return self.set_volume(new_volume)

    def volume_mute(self): return self.set_volume(self.min_volume)
    def volume_unmute(self): return self.set_volume(self.middle_volume)
    def volume_min(self): return self.set_volume(self.user_min_volume)
    def volume_middle(self): return self.set_volume(self.middle_volume)
    def volume_max(self): return self.set_volume(self.max_volume)
