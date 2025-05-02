run-local:
	python bot.py

test:
	pytest -q

lint:
	flake8 app/ bot.py

clean:
	rm -rf tmp/*
