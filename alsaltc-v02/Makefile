CC=gcc
CFLAGS=-O2 -Wall -Wextra
LTC_CFLAGS=$(shell pkg-config --cflags ltc)
LTC_LIBS=$(shell pkg-config --libs ltc)

all: alsaltc

alsaltc: alsaltc.c
	$(CC) $(CFLAGS) $(LTC_CFLAGS) alsaltc.c -o alsaltc $(LTC_LIBS) -lasound -lm -lpthread

install: alsaltc
	sudo install -m 0755 ./alsaltc /usr/local/bin/alsaltc

clean:
	rm -f alsaltc
