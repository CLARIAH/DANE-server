#!/bin/sh

# run this after you've built a new version of DANE

poetry remove dane
poetry add ../DANE/dist/*.whl
poetry build