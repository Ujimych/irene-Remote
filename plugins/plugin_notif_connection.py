from random import choice

from irene import VAApiExt

name = 'plugin_notif_connection'
version = '1.0.0'

config = {
    'phrases': [
        "Успешное соединение!",
        "Соединение установлено!",
        "Готова к работе!",
        "Жду команды!",
        "Вся в ожидании!",
    ]
}

config_comment = """
Сообщение клиенту об успешном подключении к серверу."""

def _play_notification(va: VAApiExt, _):
    va.say(choice(config['phrases']))

define_commands = {
    "соединение установлено": _play_notification,
}
