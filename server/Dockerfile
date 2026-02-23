FROM python:3.12

RUN apt-get update && apt-get install -y curl tcpdump net-tools vim

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . /code/app

EXPOSE 8000

CMD ["python", "-u", "-m", "app.server"]
#CMD ["uvicorn", "app.server:server", "--host", "0.0.0.0", "--port", "8000"]