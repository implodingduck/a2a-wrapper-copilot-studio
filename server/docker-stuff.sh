docker build -t generic-a2a-wrapper .

docker stop generic-a2a-wrapper
docker rm generic-a2a-wrapper

docker run -d -p 8000:8000 --env-file .env --name generic-a2a-wrapper generic-a2a-wrapper
docker logs -f generic-a2a-wrapper