.PHONY: install test deploy setup_service tail_logs

install:
	uv sync
	uv run pre-commit install

test:
	uv run pyright
	uv run pre-commit run --all-files

deploy:
	rsync -av --progress ./* 192.168.15.152:/home/vitor/Projetos/rpi-media/

setup_service:
	cp rpimedia.service /etc/systemd/system/
	systemctl daemon-reload
	systemctl enable rpimedia.service
	systemctl start rpimedia.service
	systemctl status rpimedia.service

tail_logs:
	journalctl -u rpimedia.service -f
