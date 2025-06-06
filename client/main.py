import yaml
import asyncio

import gateway as net
import recorder as voice
import player as audio

# Читаем конфигурационный файл
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

async def main():
    voiceRecorder = voice.Recorder( config )
    audioPlayer = audio.Player( config )

    netGateway = net.Gateway( config, '/api/face_web/ws', voiceRecorder, audioPlayer)

    await netGateway.connect()  # Устанавливаем соединение с сервером

    try:
        while True:
            await asyncio.sleep(0.1)

            # response = input("Введите команду или Q/q для выхода: ")
            # if response in ('', 'q', 'Q'):
            #     break
        
    finally:
        await netGateway.close()  # Закрываем соединение при завершении
        netGateway.task_listen_incoming.cancel()  # Останавливаем фоновый процесс приема входящих сообщений

        for task in netGateway.tasks_listen_recorder:
            task.cancel()
        netGateway.tasks_listen_recorder.clear()  # очищаем список задач

if __name__ == "__main__":
    asyncio.run(main())