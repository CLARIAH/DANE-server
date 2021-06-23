FROM python:3


COPY dane_server /src/dane_server

COPY requirements.txt /src
COPY setup.py /src
COPY README.md /src

RUN mkdir /root/.DANE
COPY config.yml /root/.DANE

WORKDIR /src

RUN pip install --no-cache-dir -r requirements.txt

RUN python setup.py install

CMD [ "python", "/src/dane_server/server.py"]