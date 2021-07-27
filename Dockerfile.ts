FROM python:3

COPY dane_server /src/dane_server

COPY requirements.txt /src
COPY setup.py /src
COPY README.md /src

# override this config in Kubernetes with a ConfigMap mounted as a volume to /root/.DANE
RUN mkdir /root/.DANE
COPY config.yml /root/.DANE

RUN mkdir /mnt/dane-fs
RUN mkdir /mnt/dane-fs/input-files
RUN mkdir /mnt/dane-fs/output-files

WORKDIR /src

RUN pip install --no-cache-dir -r requirements.txt
RUN python setup.py install

# the API does not start because of an outdated flask-restx
RUN pip install --upgrade flask-restx

CMD [ "python", "/src/dane_server/server.py"]

#ENTRYPOINT ["tail", "-f", "/dev/null"]