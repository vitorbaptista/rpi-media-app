.PHONY: install test deploy setup_service setup_crontab tail_logs ensure_video_is_playing

install:
	uv sync
	uv run pre-commit install

test:
	uv run pyright
	uv run pre-commit run --all-files

deploy:
	rsync -av --progress ./* rpi:/home/vitor/Projetos/rpi-media/

setup_service:
	cp rpimedia.service /etc/systemd/system/
	systemctl daemon-reload
	systemctl enable rpimedia.service
	systemctl start rpimedia.service
	systemctl status rpimedia.service

setup_crontab:
	crontab prod.crontab
	crontab -l

tail_logs:
	journalctl -u rpimedia.service -f

ensure_video_is_playing:
	flock --nonblock /tmp/rpi_$@.pid \
		uv run python chromecast_checker.py "https://cdn.jmvstream.com/w/LVW-9716/LVW9716_HbtQtezcaw/playlist.m3u8"https://www.youtube.com/watch?v=ha-Ag0lQmN0"; \
		rm -f /tmp/rpi_$@.pid
