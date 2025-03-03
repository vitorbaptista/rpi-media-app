install:
	uv sync
	uv run pre-commit install

test:
	uv run pre-commit run --all-files

deploy:
	rsync -av --progress ./* 192.168.50.138:/home/vitor/Projetos/rpi-media/
