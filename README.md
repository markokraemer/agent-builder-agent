# Kortix

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing.

### Prerequisites

Before you begin, ensure you have the following installed:

- Python 3.11
- Poetry

### Installation

1. Clone the repository to your local machine:

   git clone git@github.com:markokraemer/kortix.git
   cd kortix

2. Install the project dependencies using Poetry:

poetry install

3. .env Setup
Create a .env file in the root directory of the project.
Add your OpenAI API key to the .env file

OPENAI_API_KEY=your_openai_api_key


4. Building the Docker Image
Build and start the Docker containers:

docker-compose up --build -d

Access the development environment inside the Docker container:

docker-compose exec dev-env bash


# Running the App
To run the application from the base directory, use the following command:

poetry run python -m core.units.run_session

