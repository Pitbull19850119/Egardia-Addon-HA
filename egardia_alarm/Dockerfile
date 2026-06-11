ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip tzdata

COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt || \
    pip3 install --no-cache-dir -r /tmp/requirements.txt

COPY rootfs /
COPY egardia_addon.py /usr/bin/egardia_addon.py

RUN chmod a+x /usr/bin/egardia_addon.py \
    && chmod a+x /etc/services.d/egardia/run \
    && chmod a+x /etc/services.d/egardia/finish
