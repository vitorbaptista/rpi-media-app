.PHONY: install test deploy setup setup_service setup_crontab tail_logs ensure_video_is_playing play_sessao_da_tarde

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
	# Toca TV Aparecida se nada estiver tocando
	flock --nonblock /tmp/rpi_$@.pid \
		uv run python chromecast_checker.py keyboard_input c; \
		rm -f /tmp/rpi_$@.pid

play_sessao_da_tarde:
	@if uv run python get_current_media_info.py | grep -q "TV Aparecida"; then \
		flock --nonblock /tmp/rpi_sessao_da_tarde_$@.pid \
			uv run python play_sessao_da_tarde.py; \
		rm -f /tmp/rpi_sessao_da_tarde_$@.pid; \
	else \
		echo "TV Aparecida is not currently playing. Skipping play_sessao_da_tarde."; \
	fi

play_viagens_brasil:
	@if uv run python get_current_media_info.py | grep -q "TV Aparecida"; then \
		flock --nonblock /tmp/rpi_viagens_brasil_$@.pid \
			uv run rpimedia send_event keyboard_input b --max-enqueued-videos 0; \
		rm -f /tmp/rpi_viagens_brasil_$@.pid; \
	else \
		echo "TV Aparecida is not currently playing. Skipping play_viagens_brasil."; \
	fi
