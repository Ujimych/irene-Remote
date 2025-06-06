Клиент для [голосового ассистента Ирина] (https://github.com/janvarev/Irene-Voice-Assistant)в модификации от [AlexeyBond] (https://github.com/AlexeyBond/Irene-Voice-Assistant) предназначенный для устройств поддерживающих python, таких как raspberry pi.
Для лучшего захвата звука рекомендую использование платы расширения [ReSpeaker 2-Mics Pi HAT] (https://wiki.seeedstudio.com/ReSpeaker_2_Mics_Pi_HAT_Raspberry/), но возможно использование других микрофонов

## Основной функционал:
- получение звука с микрофона и пересылка на сервер Ирины для распознавания
- воспроизведение звуковых файлов полученных с сервера.

## Дополнительный функционал:
- во время отсутствия соединения с сервером горит светодиод подключенный к 13 пину

## Установка:
устанавливаем зависимости
sudo apt-get install python3-dev libffi-dev gcc make portaudio19-dev

Если используется «ReSpeaker 2-Mics Pi HAT» произведите установку и настройку согласно [рекомендациям] (https://wiki.seeedstudio.com/ReSpeaker_2_Mics_Pi_HAT_Raspberry/)

клонируйте клиент 
git clone https://github.com/Ujimych/irene-Remote/client irene-Remote

В папке проекта создадим все необходимое для виртуального окружения
cd irene-Remote
python3 -m venv .
source bin/activate

Установим библиотеки 
pip install -r requirements.txt

Настроим файл конфигурации «config.yaml» в папке проекта, указав адрес сервера «Ирины» и отредактировав, если необходимо, устройства ввода и вывода звука

и можем запускать клиент
python3 main.py

После полной настройки и проверки работы клиента, его можно запустить в качестве сервиса, для автоматического запуска после перезагрузки устройства.
