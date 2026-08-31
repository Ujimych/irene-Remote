from random import choice

from irene import VAApiExt
from irene.brain.abc import OutputChannel

name = 'plugin_listen'
version = '0.2.0'

config = {
    'phrases_success': [
        "Слушаю",
        "Внимательно слушаю",
    ],
    'phrases_unsuccessful': [
        "Не удалось включить режим прослушивания",
        "Не удалось",
        "Возникла проблема",
    ],
}

def _is_listen_channel(channel: OutputChannel) -> bool:
    return callable(getattr(channel, 'listen', None))

def _get_listen_channel(va: VAApiExt):
    print("LISTEN DEBUG: _get_listen_channel called")
    try:
        related = va.get_message().get_related_outputs()
        print("LISTEN DEBUG: related outputs:", [type(channel).__name__ for channel in related])
    except Exception as e:
        print("LISTEN DEBUG: related outputs ERROR:", repr(e))

    try:
        outputs = va.get_outputs()
        print("LISTEN DEBUG: global outputs:", [type(channel).__name__ for channel in outputs])
    except Exception as e:
        print("LISTEN DEBUG: global outputs ERROR:", repr(e))

    channels = va.get_outputs_preferring_relevant(OutputChannel, _is_listen_channel)
    print("LISTEN DEBUG: FOUND:", [f"{type(channel).__module__}.{type(channel).__name__}" for channel in channels])

    if not channels: raise RuntimeError("Не найден канал вывода с поддержкой режима «Слушай»")
    return channels[0]

def _is_valid_listen_command(full_text: str) -> bool:
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
        for variant in command.split("|"): valid_commands.add(tuple(variant.split()))

    return tuple(words) in valid_commands

def _execute_listen_command(va: VAApiExt, _text: str):
    print("LISTEN DEBUG: _execute_listen_command")
    try:
        full_text = va.get_message().get_original().get_text().strip().lower()
    except Exception as e:
        print("LISTEN DEBUG: не удалось получить исходный текст:", repr(e))
        va.say(choice(config['phrases_unsuccessful']))
        return

    print(f"LISTEN DEBUG: full_text={full_text!r}")
    if not _is_valid_listen_command(full_text):
        print("LISTEN DEBUG: command rejected")
        va.say(choice(config['phrases_unsuccessful']))
        return

    print("LISTEN DEBUG: command accepted")
    try:
        channel = _get_listen_channel(va)
        result = channel.listen()
        print(f"LISTEN DEBUG: listen() -> {result!r}")

        if result.success:
            print("LISTEN DEBUG: режим «Слушай» успешно включён.")
            va.say(choice(config['phrases_success']))
        else:
            print("LISTEN DEBUG: клиент не смог включить режим «Слушай».")
            va.say(choice(config['phrases_unsuccessful']))
    except Exception as e:
        print("LISTEN DEBUG: listen ERROR:", repr(e))
        va.say(choice(config['phrases_unsuccessful']))

define_commands = {
    "слушай": _execute_listen_command,
    "внимание": _execute_listen_command,
    "тишина": _execute_listen_command,
}
