from random import choice

from irene import VAApiExt
from irene.brain.abc import OutputChannel

name = 'plugin_volume_commands'
version = '1.3.0'

config = {
    'phrases_success': [
        "Готово",
        "Исполнено",
        "Выполнила",
        "Применила",
    ],
    'phrases_unsuccessful': [
        "Не удалось изменить громкость",
        "Не удалось",
        "Возникла проблема",
    ],
}

_UNITS = {
    "ноль": 0,
    "один": 1,
    "два": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
}

_TENS = {
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
}

_HUNDREDS = {
    "сто": 100,
}

def _parse_number(text: str):
    text = text.strip().lower()
    if not text: return None

    if text.isdigit():
        value = int(text)
        return value if 0 <= value <= 100 else None

    words = text.split()
    if len(words) == 1:
        word = words[0]
        if word in _UNITS: return _UNITS[word]
        if word in _TENS: return _TENS[word]
        if word in _HUNDREDS: return _HUNDREDS[word]
        return None

    if len(words) == 2:
        tens = _TENS.get(words[0])
        units = _UNITS.get(words[1])
        if tens is not None and units is not None:
            value = tens + units
            if 0 <= value <= 100: return value

    return None

def _is_volume_channel(channel: OutputChannel) -> bool:
    return callable(getattr(channel, 'volume_up', None)) and callable(getattr(channel, 'volume_down', None)) and callable(getattr(channel, 'set_volume', None)) and callable(getattr(channel, 'get_volume', None))

def _get_volume_channel(va: VAApiExt):
    print("VOLUME DEBUG: _get_volume_channel called")
    try:
        related = va.get_message().get_related_outputs()
        print("VOLUME DEBUG: related outputs:", [type(channel).__name__ for channel in related])
    except Exception as e:
        print("VOLUME DEBUG: related outputs ERROR:", repr(e))

    try:
        outputs = va.get_outputs()
        print("VOLUME DEBUG: global outputs:", [type(channel).__name__ for channel in outputs])
    except Exception as e:
        print("VOLUME DEBUG: global outputs ERROR:", repr(e))

    channels = va.get_outputs_preferring_relevant(OutputChannel, _is_volume_channel)
    print("VOLUME DEBUG: FOUND:", [f"{type(channel).__module__}.{type(channel).__name__}" for channel in channels])

    if not channels: raise RuntimeError("Не найден канал вывода с поддержкой регулировки громкости")
    return channels[0]

def _is_valid_volume_command(full_text: str) -> bool:
    words = full_text.split()
    from irene.brain.brain_plugin import BrainPlugin
    trigger_phrases = BrainPlugin.config['triggerPhrases']

    for phrase in trigger_phrases:
        trigger_words = phrase.split()
        if words[:len(trigger_words)] == trigger_words:
            words = words[len(trigger_words):]
            break

    valid_commands = set()
    for command in define_commands:
        if command == "громкость": continue
        for variant in command.split("|"): valid_commands.add(tuple(variant.split()))

    return tuple(words) in valid_commands

def _execute_volume_command(va: VAApiExt, command, text: str):
    full_text = va.get_message().get_original().get_text().strip()
    print(f"VOLUME DEBUG: command = {command.__name__}")
    print(f"VOLUME DEBUG: full_text = {full_text!r}")

    if not _is_valid_volume_command(full_text):
        print("VOLUME DEBUG: command rejected")
        va.say(choice(config['phrases_unsuccessful']))
        return

    print("VOLUME DEBUG: command accepted")
    try:
        channel = _get_volume_channel(va)
        result = command(channel)
        if result.success: va.say(choice(config['phrases_success']))
        else: va.say(choice(config['phrases_unsuccessful']))
    except Exception as e:
        print(f"VOLUME DEBUG: {command.__name__} ERROR:", repr(e))
        va.say(choice(config['phrases_unsuccessful']))

def _volume_up(va: VAApiExt, _text: str): _execute_volume_command(va, lambda channel: channel.volume_up(), _text)
def _volume_down(va: VAApiExt, _text: str): _execute_volume_command(va, lambda channel: channel.volume_down(), _text)
def _volume_mute(va: VAApiExt, _text: str): _execute_volume_command(va, lambda channel: channel.mute(), _text)
def _volume_unmute(va: VAApiExt, _text: str): _execute_volume_command(va, lambda channel: channel.unmute(), _text)
def _volume_min(va: VAApiExt, _text: str): _execute_volume_command(va, lambda channel: channel.volume_min(), _text)
def _volume_middle(va: VAApiExt, _text: str): _execute_volume_command(va, lambda channel: channel.volume_middle(), _text)
def _volume_max(va: VAApiExt, _text: str): _execute_volume_command(va, lambda channel: channel.volume_max(), _text)

def _volume_set(va: VAApiExt, text: str):
    print("VOLUME DEBUG: _volume_set")
    print(f"VOLUME DEBUG: text = {text!r}")

    value = _parse_number(text)
    print(f"VOLUME DEBUG: parsed value = {value!r}")

    if value is None:
        print("VOLUME DEBUG: не удалось распознать число")
        va.say(choice(config['phrases_unsuccessful']))
        return

    if not 0 <= value <= 100:
        print(f"VOLUME DEBUG: значение вне диапазона 0..100: {value}")
        va.say(choice(config['phrases_unsuccessful']))
        return

    try:
        channel = _get_volume_channel(va)
        result = channel.set_volume(value)
        print(f"VOLUME DEBUG: set_volume({value}) -> {result!r}")

        if result.success:
            va.say(choice(config['phrases_success']))
        else:
            va.say(choice(config['phrases_unsuccessful']))

    except Exception as e:
        print("VOLUME DEBUG: set_volume ERROR:", repr(e))
        va.say(choice(config['phrases_unsuccessful']))

def _volume_get(va: VAApiExt, _text: str):
    print("VOLUME DEBUG: _volume_get")
    try:
        channel = _get_volume_channel(va)
        result = channel.get_volume()
        print(f"VOLUME DEBUG: get_volume() -> {result!r}")

        if not result.success:
            print("VOLUME DEBUG: не удалось получить громкость")
            va.say(choice(config['phrases_unsuccessful']))
            return

        volume = result.volume
        if volume is None:
            print("VOLUME DEBUG: сервер не вернул значение громкости")
            va.say(choice(config['phrases_unsuccessful']))
            return

        volume = int(volume)
        print(f"VOLUME DEBUG: текущая громкость = {volume}%")
        va.say(f"громкость {volume} процентов")

    except Exception as e:
        print("VOLUME DEBUG: get_volume ERROR:", repr(e))
        va.say(choice(config['phrases_unsuccessful']))



define_commands = {
    "назови уровень громкости": _volume_get,
    "назови уровень": _volume_get,
    "какая громкость": _volume_get,
    "какой уровень громкости": _volume_get,
    "уровень громкости": _volume_get,

    "громче": _volume_up,
    "увеличь громкость": _volume_up,

    "тише": _volume_down,
    "уменьши громкость": _volume_down,

    "без звука": _volume_mute,
    "звук": _volume_unmute,

    "минимальная громкость": _volume_min,
    "минимальный звук": _volume_min,

    "средняя громкость": _volume_middle,
    "средний звук": _volume_middle,

    "максимальная громкость": _volume_max,
    "максимальный звук": _volume_max,

    "громкость": _volume_set,
}
