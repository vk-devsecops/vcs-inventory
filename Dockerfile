FROM python:3.11-alpine

ARG USERNAME=non-root-user
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN apk add --no-cache shadow

COPY . /inventory

RUN python -m pip install -r /inventory/requirements.txt

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && chown -R $USER_GID /inventory \
    && chmod -R 770  /inventory

WORKDIR /inventory

USER $USERNAME

CMD ["python", "./inventory.py"]
