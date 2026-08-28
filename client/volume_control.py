import logging
import subprocess


class VolumeControl:
    """
    Управление аппаратной громкостью аудиовыхода.

    Используется регулятором Speaker звуковой карты
    Seeed 2-Mic Voice Card.
    """

    def __init__(self, in_config):
        self.volume_step = in_config["volume_step"]

        self.mixer_card = in_config["mixer"]["card"]
        self.mixer_control = in_config["mixer"]["control"]

        self.min_volume = in_config["volume"]["min"]
        self.middle_volume = in_config["volume"]["middle"]
        self.max_volume = in_config["volume"]["max"]

        self._logger = logging.getLogger("VolumeControl")
        self._logger.setLevel(logging.DEBUG)

        if not self._logger.handlers:
            console_handler = logging.StreamHandler()

            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            )

            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        # При запуске клиента устанавливаем среднюю громкость.
        self.set_volume(self.middle_volume)

    def get_volume(self):
        """Получить текущую громкость Speaker."""
        try:
            result = subprocess.run(
                [
                    "amixer",
                    "-c",
                    self.mixer_card,
                    "get",
                    self.mixer_control
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

            for line in result.stdout.splitlines():
                if "Front Left:" in line:
                    value = (
                        line.split("Playback")[1]
                        .split("[")[0]
                        .strip()
                    )

                    volume = int(value)

                    self._logger.debug(
                        f"Текущая громкость: {volume}"
                    )

                    return volume

            raise RuntimeError(
                "Не удалось определить текущую громкость."
            )

        except Exception as e:
            self._logger.exception(
                f"Ошибка получения громкости: {e}"
            )

            return None

    def set_volume(self, volume):
        """Установить громкость Speaker."""
        try:
            volume = max(
                self.min_volume,
                min(self.max_volume, int(volume))
            )

            subprocess.run(
                [
                    "amixer",
                    "-c",
                    self.mixer_card,
                    "set",
                    self.mixer_control,
                    str(volume)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

            self._logger.info(
                f"Громкость установлена: {volume}"
            )

            return True

        except Exception as e:
            self._logger.exception(
                f"Ошибка установки громкости: {e}"
            )

            return False

    def volume_up(self):
        """Увеличить громкость на volume_step."""
        current_volume = self.get_volume()

        if current_volume is None:
            return False

        new_volume = min(
            self.max_volume,
            current_volume + self.volume_step
        )

        return self.set_volume(new_volume)

    def volume_down(self):
        """Уменьшить громкость на volume_step."""
        current_volume = self.get_volume()

        if current_volume is None:
            return False

        new_volume = max(
            self.min_volume,
            current_volume - self.volume_step
        )

        return self.set_volume(new_volume)

    def volume_mute(self):
        """Установить минимальную громкость."""
        return self.set_volume(self.min_volume)

    def volume_unmute(self):
        """Восстановить среднюю громкость."""
        return self.set_volume(self.middle_volume)

    def volume_min(self):
        """Установить минимальную громкость."""
        return self.set_volume(self.min_volume)

    def volume_middle(self):
        """Установить среднюю громкость."""
        return self.set_volume(self.middle_volume)

    def volume_max(self):
        """Установить максимальную громкость."""
        return self.set_volume(self.max_volume)
