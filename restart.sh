#!/bin/bash

pid=$(pgrep -f handle_notify.py)
echo $pid
if [[ "$pid" =~ ^[0-9]+$ ]]; then
	$(kill -9 $pid)
	sleep 5
	python handle_notify.py
fi
