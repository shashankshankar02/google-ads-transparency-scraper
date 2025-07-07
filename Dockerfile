# Use Apify's base image with Python and Chrome
FROM apify/actor-python-selenium

# Install tesseract-ocr and Chrome
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    wget \
    gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /usr/src/app

# Copy requirements first for better caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . ./

# Run the scraper
CMD ["python", "main.py"]

LABEL com.apify.actBuildId=ICAlZ9TcdpNfodg5J 