#!/bin/bash

bash init_db.sh
gunicorn app:app