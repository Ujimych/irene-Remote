Плагин для [голосового ассистента Ирина] (https://github.com/janvarev/Irene-Voice-Assistant)в модификации от [AlexeyBond] (https://github.com/AlexeyBond/Irene-Voice-Assistant)

Данный плагин создает голосовое оповещение об успешном подключении клиента к серверу "Ирины"

## Установка

Плагины:
   - 'plugin_notif_connection.py'
   - 'plugin_volume_commands.py'

устанавливаем на сервер Ирины в папку 'plugins'

Плагин:
   - 'plugin_out_volume.py'

устанавливаем так же на сервер Ирины но в папку 'irene_plugin_web_face'

дополнительно необходимо внести изменения в 'protocol.py' находящийся в папке 'irene_plugin_web_face'
дополняя его строками:

PROTOCOL_OUT_VOLUME = 'out.volume'

MT_OUT_VOLUME_COMMAND = f'{PROTOCOL_OUT_VOLUME}/command'

MT_OUT_VOLUME_RESULT = f'{PROTOCOL_OUT_VOLUME}/result'


После копирования файлов и внесения изменений, обязательно перезапускаем сервер Ирины


