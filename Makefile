run-local: ; python bot.py
test:      ; pytest -q
lint:      ; black . --check
clean:     ; rm -rf tmp/*
