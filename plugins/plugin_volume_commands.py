from random import choice

from irene import VAApiExt
from irene.brain.abc import OutputChannel


name = 'plugin_volume_commands'
version = '1.1.0'


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


def _is_volume_channel(channel: OutputChannel) -> bool:
    return (
        callable(getattr(channel, 'volume_up', None))
        and callable(getattr(channel, 'volume_down', None))
    )


def _get_volume_channel(va: VAApiExt):
    print("VOLUME DEBUG: _get_volume_channel called")

    try:
        related = va.get_message().get_related_outputs()
        print(
            "VOLUME DEBUG: related outputs:",
            [type(ch).__name__ for ch in related]
        )
    except Exception as e:
        print("VOLUME DEBUG: related outputs ERROR:", repr(e))

    try:
        outputs = va.get_outputs()
        print(
            "VOLUME DEBUG: global outputs:",
            [type(ch).__name__ for ch in outputs]
        )
    except Exception as e:
        print("VOLUME DEBUG: global outputs ERROR:", repr(e))

    channels = va.get_outputs_preferring_relevant(
        OutputChannel,
        _is_volume_channel,
    )

    print(
        "VOLUME DEBUG: FOUND:",
        [
            f"{type(ch).__module__}.{type(ch).__name__}"
            for ch in channels
        ]
    )

    if not channels:
        raise RuntimeError(
            "Не найден канал вывода с поддержкой регулировки громкости"
        )

    return channels[0]


def _is_valid_volume_command(full_text: str) -> bool:
    words = full_text.split()

    # Получаем настроенные фразы обращения к ассистенту.
    from irene.brain.brain_plugin import BrainPlugin

    trigger_phrases = BrainPlugin.config['triggerPhrases']

    # Убираем имя/фразу ассистента из начала команды.
    for phrase in trigger_phrases:
        trigger_words = phrase.split()

        if words[:len(trigger_words)] == trigger_words:
            words = words[len(trigger_words):]
            break

    valid_commands = set()

    for command in define_commands:
        for variant in command.split("|"):
            valid_commands.add(tuple(variant.split()))

    return tuple(words) in valid_commands


def _execute_volume_command(
        va: VAApiExt,
        command,
        text: str,
):
    full_text = va.get_message().get_original().get_text().strip()

    print("==========================")
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

        if result.success:
            va.say(choice(config['phrases_success']))
        else:
            va.say(choice(config['phrases_unsuccessful']))

    except Exception as e:
        print(
            f"VOLUME DEBUG: {command.__name__} ERROR:",
            repr(e)
        )
        va.say(choice(config['phrases_unsuccessful']))


def _volume_up(va: VAApiExt, _text: str):
    _execute_volume_command(
        va,
        lambda channel: channel.volume_up(),
        _text,
    )


def _volume_down(va: VAApiExt, _text: str):
    _execute_volume_command(
        va,
        lambda channel: channel.volume_down(),
        _text,
    )


def _volume_mute(va: VAApiExt, _text: str):
    _execute_volume_command(
        va,
        lambda channel: channel.mute(),
        _text,
    )


def _volume_unmute(va: VAApiExt, _text: str):
    _execute_volume_command(
        va,
        lambda channel: channel.unmute(),
        _text,
    )


def _volume_min(va: VAApiExt, _text: str):
    print("==========================")
    print("VOLUME DEBUG: _volume_min")

    full_text = va.get_message().get_original().get_text().strip()

    if not _is_valid_volume_command(full_text):
        print("VOLUME DEBUG: command rejected")
        va.say(choice(config['phrases_unsuccessful']))
        return

    try:
        channel = _get_volume_channel(va)
        result = channel.volume_min()

        if result.success:
            va.say(choice(config['phrases_success']))
        else:
            va.say(choice(config['phrases_unsuccessful']))
    except Exception as e:
        print("VOLUME DEBUG: volume_min ERROR:", repr(e))
        va.say(choice(config['phrases_unsuccessful']))


def _volume_middle(va: VAApiExt, _text: str):
    print("==========================")
    print("VOLUME DEBUG: _volume_middle")

    full_text = va.get_message().get_original().get_text().strip()

    if not _is_valid_volume_command(full_text):
        print("VOLUME DEBUG: command rejected")
        va.say(choice(config['phrases_unsuccessful']))
        return

    try:
        channel = _get_volume_channel(va)
        result = channel.volume_middle()

        if result.success:
            va.say(choice(config['phrases_success']))
        else:
            va.say(choice(config['phrases_unsuccessful']))
    except Exception as e:
        print("VOLUME DEBUG: volume_middle ERROR:", repr(e))
        va.say(choice(config['phrases_unsuccessful']))


def _volume_max(va: VAApiExt, _text: str):
    print("==========================")
    print("VOLUME DEBUG: _volume_max")

    full_text = va.get_message().get_original().get_text().strip()

    if not _is_valid_volume_command(full_text):
        print("VOLUME DEBUG: command rejected")
        va.say(choice(config['phrases_unsuccessful']))
        return

    try:
        channel = _get_volume_channel(va)
        result = channel.volume_max()

        if result.success:
            va.say(choice(config['phrases_success']))
        else:
            va.say(choice(config['phrases_unsuccessful']))
    except Exception as e:
        print("VOLUME DEBUG: volume_max ERROR:", repr(e))
        va.say(choice(config['phrases_unsuccessful']))


define_commands = {
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
}
