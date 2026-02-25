docker build -t a2a-wrapper-copilot-studio .

docker stop a2a-wrapper-copilot-studio
docker rm a2a-wrapper-copilot-studio

docker run -d -p 8000:8000 --env-file .env --name a2a-wrapper-copilot-studio a2a-wrapper-copilot-studio
docker logs -f a2a-wrapper-copilot-studio