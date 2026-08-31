import asyncio

import yaml

import gateway as net
import recorder as voice
import player as audio
import mpd_player
import volume_control

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

async def main():
    voice_recorder = voice.Recorder(config)
    audio_player = audio.Player(config)
    mpd_player_instance = mpd_player.MpdPlayer(host="localhost", port=6600, volume_step=10)
    volume_control_instance = volume_control.VolumeControl(config)

    gateway = net.Gateway(config, "/api/face_web/ws", voice_recorder, audio_player, mpd_player_instance, volume_control_instance)
    await gateway.connect()

    try:
        while True: await asyncio.sleep(1)
    finally:
        voice_recorder.resume(False)
        if gateway.task_listen_incoming is not None: gateway.task_listen_incoming.cancel()
        if gateway.task_listen_second_connection is not None: gateway.task_listen_second_connection.cancel()
        for task in gateway.tasks_listen_recorder: task.cancel()
        gateway.tasks_listen_recorder.clear()
        await gateway.close()
        mpd_player_instance.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Завершение программы.")
