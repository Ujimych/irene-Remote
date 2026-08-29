import logging
import subprocess


class VolumeControl:
    """
    Управление аппаратной громкостью аудиовыхода.

    Используется регулятором Speaker звуковой карты
    Seeed 2-Mic Voice Card.

    Аппаратный диапазон:
        min .. max

    Пользовательская шкала:
        user_min .. max -> 0 .. 100%

    Например:
        user_min = 76  -> 0%
        middle   = 112 -> 50%
        max      = 127 -> 100%
    """

    def __init__(self, in_config):
        # ------------------------------------------------------
        # Основные настройки
        # ------------------------------------------------------

        self.volume_step = int(
            in_config["volume_step"]
        )

        # ------------------------------------------------------
        # ALSA mixer
        # ------------------------------------------------------

        self.mixer_card = str(
            in_config["mixer"]["card"]
        )

        self.mixer_control = str(
            in_config["mixer"]["control"]
        )

        # ------------------------------------------------------
        # Аппаратный диапазон громкости
        # ------------------------------------------------------

        self.min_volume = int(
            in_config["volume"]["min"]
        )

        self.user_min_volume = int(
            in_config["volume"]["user_min"]
        )

        self.middle_volume = int(
            in_config["volume"]["middle"]
        )

        self.max_volume = int(
            in_config["volume"]["max"]
        )

        # ------------------------------------------------------
        # Проверка конфигурации
        # ------------------------------------------------------

        if not (
            self.min_volume
            <= self.user_min_volume
            <= self.middle_volume
            <= self.max_volume
        ):
            raise ValueError(
                "Некорректная конфигурация громкости: "
                "должно выполняться "
                "min <= user_min <= middle <= max."
            )

        if self.volume_step <= 0:
            raise ValueError(
                "volume_step должен быть больше 0."
            )

        # ------------------------------------------------------
        # Логирование
        # ------------------------------------------------------

        self._logger = logging.getLogger(
            "VolumeControl"
        )

        self._logger.setLevel(logging.DEBUG)

        if not self._logger.handlers:
            console_handler = logging.StreamHandler()

            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            )

            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        # ------------------------------------------------------
        # При запуске клиента устанавливаем среднюю громкость.
        # ------------------------------------------------------

        self.set_volume(
            self.middle_volume
        )

    # ==========================================================
    # Получение аппаратной громкости
    # ==========================================================

    def get_volume(self):
        """
        Получить текущую аппаратную громкость Speaker.

        Возвращает значение из диапазона:
            min_volume .. max_volume
        """

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
                        f"Текущая аппаратная громкость: "
                        f"{volume}"
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

    # ==========================================================
    # Установка аппаратной громкости
    # ==========================================================

    def set_volume(self, volume):
        """
        Установить аппаратную громкость Speaker.

        Значение автоматически ограничивается диапазоном:
            min_volume .. max_volume
        """

        try:

            volume = max(
                self.min_volume,
                min(
                    self.max_volume,
                    int(volume)
                )
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

    # ==========================================================
    # Преобразование аппаратной громкости в проценты
    # ==========================================================

    def volume_to_percent(self, volume):
        """
        Преобразовать аппаратное значение громкости
        в пользовательские проценты 0..100.

        user_min_volume -> 0%
        middle_volume   -> 50%
        max_volume      -> 100%

        Значения ниже user_min_volume также считаются 0%.
        """

        try:
            volume = int(volume)

            if volume <= self.user_min_volume:
                return 0

            if volume >= self.max_volume:
                return 100

            percent = round(
                (
                    (volume - self.user_min_volume)
                    /
                    (self.max_volume - self.user_min_volume)
                )
                * 100
            )

            return max(
                0,
                min(100, percent)
            )

        except (TypeError, ValueError):

            self._logger.exception(
                f"Ошибка преобразования громкости "
                f"в проценты: {volume}"
            )

            return None

    # ==========================================================
    # Преобразование процентов в аппаратную громкость
    # ==========================================================

    def percent_to_volume(self, percent):
        """
        Преобразовать пользовательские проценты 0..100
        в аппаратное значение громкости.

        0%   -> user_min_volume
        50%  -> середина пользовательского диапазона
        100% -> max_volume
        """

        try:

            percent = max(
                0,
                min(100, int(percent))
            )

            volume = round(
                self.user_min_volume
                +
                (
                    (
                        self.max_volume
                        - self.user_min_volume
                    )
                    * percent
                    / 100
                )
            )

            return max(
                self.user_min_volume,
                min(self.max_volume, volume)
            )

        except (TypeError, ValueError):

            self._logger.exception(
                f"Ошибка преобразования процентов "
                f"в громкость: {percent}"
            )

            return None

    # ==========================================================
    # Получение громкости в процентах
    # ==========================================================

    def get_volume_percent(self):
        """
        Получить текущую громкость
        в пользовательских процентах 0..100.
        """

        volume = self.get_volume()

        if volume is None:
            return None

        percent = self.volume_to_percent(
            volume
        )

        self._logger.debug(
            f"Пользовательская громкость: "
            f"{percent}%"
        )

        return percent

    # ==========================================================
    # Установка громкости в процентах
    # ==========================================================

    def set_volume_percent(self, percent):
        """
        Установить громкость в пользовательских процентах.

        Диапазон:
            0..100%

        Значение переводится в аппаратный диапазон
        и передается в ALSA.
        """

        volume = self.percent_to_volume(
            percent
        )

        if volume is None:
            return False

        self._logger.info(
            f"Установка громкости: "
            f"{percent}% -> {volume}"
        )

        return self.set_volume(
            volume
        )

    # ==========================================================
    # Увеличение громкости
    # ==========================================================

    def volume_up(self):
        """
        Увеличить громкость на volume_step.
        """

        current_volume = self.get_volume()

        if current_volume is None:
            return False

        new_volume = min(
            self.max_volume,
            current_volume + self.volume_step
        )

        return self.set_volume(
            new_volume
        )

    # ==========================================================
    # Уменьшение громкости
    # ==========================================================

    def volume_down(self):
        """
        Уменьшить громкость на volume_step.
        """

        current_volume = self.get_volume()

        if current_volume is None:
            return False

        new_volume = max(
            self.user_min_volume,
            current_volume - self.volume_step
        )

        return self.set_volume(
            new_volume
        )

    # ==========================================================
    # Предустановленные уровни
    # ==========================================================

    def volume_mute(self):
        """
        Установить минимальную аппаратную громкость.

        Это физический mute — 0.
        """

        return self.set_volume(
            self.min_volume
        )

    def volume_unmute(self):
        """
        Восстановить среднюю громкость.
        """

        return self.set_volume(
            self.middle_volume
        )

    def volume_min(self):
        """
        Установить пользовательский 0%.

        Это не обязательно физический 0.
        """

        return self.set_volume(
            self.user_min_volume
        )

    def volume_middle(self):
        """
        Установить среднюю громкость.
        """

        return self.set_volume(
            self.middle_volume
        )

    def volume_max(self):
        """
        Установить максимальную громкость.
        """

        return self.set_volume(
            self.max_volume
        )
