.PHONY: install test deploy setup setup_service setup_crontab tail_logs ensure_video_is_playing play_sessao_da_tarde play_musica mute_before_dawn hearing_aids_schedule

install:
	uv sync
	uv run pre-commit install

test:
	uv run pyright
	uv run pre-commit run --all-files

deploy:
	rsync -av --progress ./* rpi:/home/vitor/Projetos/rpi-media/

setup: setup_crontab
	sudo make setup_service

setup_service:
	cp rpimedia.service /etc/systemd/system/
	systemctl daemon-reload
	systemctl enable rpimedia.service
	systemctl restart rpimedia.service
	systemctl status rpimedia.service

setup_crontab:
	crontab prod.crontab
	crontab -l

tail_logs:
	journalctl -u rpimedia.service -f

ensure_video_is_playing:
	# Resume se algum app estiver pausado, senão toca TV Aparecida
	flock --nonblock /tmp/rpi_$@.lock \
		sh -c 'uv run rpimedia resume; uv run rpimedia is_playing || uv run rpimedia send_event keyboard_input c'

mute_before_dawn:
	# Volume zero pelas manhãs. Sono é importante.
	flock --nonblock /tmp/rpi_$@.lock \
		uv run python mute_before_dawn.py 05:30 80

play_sessao_da_tarde:
	flock --nonblock /tmp/rpi_$@.lock \
		sh -c 'uv run rpimedia is_playing && uv run python play_sessao_da_tarde.py'

play_viagens_brasil:
	flock --nonblock /tmp/rpi_$@.lock \
		sh -c 'uv run rpimedia is_playing && uv run rpimedia send_event keyboard_input b --max-enqueued-videos 0'

play_musica:
	flock --nonblock /tmp/rpi_$@.lock \
		sh -c 'uv run rpimedia is_playing && uv run rpimedia send_event keyboard_input f --max-enqueued-videos 0'

hearing_aids_schedule:
	# Connect hearing aids 05:00–11:00, disconnect otherwise. Acts only
	# on transitions, so frequent cron ticks are safe (and provide retry
	# on transient failure).
	flock --nonblock /tmp/rpi_$@.lock \
		uv run rpimedia hearing_aids_schedule 05:00 11:00
