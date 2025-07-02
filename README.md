# ALActions - Github Actions for the Assembly Line project

Shared actions, used over many different [Assembly Line projets](https://suffolklitlab.org/docassemble-AssemblyLine-documentation/docs/).

## Usage

You can use the actions in repo github workflows by refering the subfolder of the desired action and
the a specific branch or tagged version you want to run:

```yml
jobs:
  my-workflow:
    ...
    steps:
      - uses: SuffolkLITLab/ALActions/pythontests@main 
```

For assembly line projects, you should refer to the `main` branch, as that will allow 
bug fixes to the actions to immediately propagate to the AssemblyLine repos.

## The Actions

### pythontest

`pythontest` sets up a python environment around the package, and runs any [`unittest` tests](https://docs.python.org/3/library/unittest.html) in the package.

#### Usage

```yml
jobs:
  my-workflow:
    ...
    # No inputs
    steps:
      - uses: SuffolkLITLab/ALActions/pythontests@main 
```

### black-formatting

#### Usage  

```yml
jobs:
  my-workflow:
    ...
    steps:
      - uses: SuffolkLITLab/ALActions/black-formatting@main
        with:
          MAKE_PR: "true"
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`black` will also read configs from `pyproject.toml`. In most projects, we include the following:

```toml
[tool.black]
extend-exclude = '(__init__.py|setup.py)'
```

### da_playground_install

`playground_install` mirrors the options of the Docassemble /api/playground_install endpoint.

It can be used to install the contents of a repository to a specified Docassemble playground
and project. This can be useful to make it simple to do interactive end-to-end testing of
new versions of your project, especially if you want to enable testing of multiple versions
on a single server.

#### Usage

Create a new file in .github/workflows/, named "playground_publish.yml" or a .yml 
name of your choice.

The contents should look like:

```yaml
name: Deploy to Docassemble Playground
on:
  push:
    branches:
      - main  # Trigger the workflow on push to main branch
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v3
      - name: Deploy to Docassemble Playground
        uses: SuffolkLITLab/ALActions/da_playground_install@dogfood
        with:
          SERVER_URL: ${{ secrets.SERVER_URL }}
          DOCASSEMBLE_DEVELOPER_API_KEY: ${{ secrets.DOCASSEMBLE_DEVELOPER_API_KEY }}
          PROJECT_NAME: ${{ secrets.PROJECT_NAME }}
```

You can either directly edit the SERVER_URL and PROJECT_NAME parameters, or add them as
GitHub repository secrets. The server URL should look like this:

`https://apps-dev.example.com`, without the trailing slash.

### da_package

The `da_package` action is like the `da_playground_install` action, except that it
installs the current GitHub repository server-wide.

While it can be used to install the package directly from the repository by uploading
it as a .zip file, typically you will want to use the GitHub url instead to make it
possible to click the `update` button manually.

### docsig

`docsig` checks all of the docstrings in the python package to ensure that they match the function signature and have consistent styles.
Since we use Google style for our docstrings, the packages should use that, even though `docsig` allows NumPy and sphinx styles as well.

#### Usage


```yml
jobs:
  my-workflow:
    ...
    steps:
      - uses: SuffolkLITLab/ALActions/docsig@main
```

`docsig` can be configured by using `pyproject.toml`. See [the docsig README.md](https://github.com/jshwi/docsig/tree/v0.35.0#commandline) for more info.


### publish

`publish` publishes a python package to pypi, and announces the publishing to a given Teams chat.

#### Usage

```yml
jobs:
  my-workflow:
    ...
    steps:
    - uses: SuffolkLITLab/ALActions/publish@main
      with:
        PYPI_API_TOKEN: ${{ secrets.PYPI_API_TOKEN }}
        VERSION_TO_PUBLISH: ${{ env.GITHUB_REF_NAME }}
        TEAMS_BUMP_WEBHOOK: ${{ secrets.TEAMS_BUMP_WEBHOOK }}
```

### Hall Monitor

`hall_monitor` checks a given docassemble server to make sure that all of the installed interviews can load their first page correctly,
acting like a hall monitor peaking through doors, but not investigating any further.

#### Usage

You will likely want to run this action on a schedule, several times a day.
You can see more about how to define this schedule in the
[github on.schedule](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#onschedule)
documentation.

```yml
on:
  schedule:
    # Runs at 6:00am, and 18:00 (6:00pm)
    - cron: "0 6,18 * * *"

jobs:
  my-workflow:
    ...
    steps:
      - uses: SuffolkLITLab/ALActions/hall_monitor@main
        with:
          SERVER_URL: "https://my-docassemble.example.com"
```

This also supports sending email notifications (separate from GitHub's notification system, which doesn't let you notify arbitrary people about an action failing) to multiple, comma separated emails, using [Sendgrid](https://sendgrid.com/) and [Mailgun](https://www.mailgun.com/).

Here's a code example for sendgrid:

```yml
jobs:
  my-workflow:
    ...
    steps:
      - uses: SuffolkLITLab/ALActions/hall_monitor@main
        with:
          SERVER_URL: "https://my-docassemble.example.com"
          SENDGRID_API_KEY: ${{ secrets.MY_SENDGRID_API_KEY }}
          ERROR_FROM_EMAIL: Monitor <alert@example.com>
          ERROR_EMAILS: example@example.com,example2@example.com
```

And one for Mailgun

```yml
jobs:
  my-workflow:
    ...
    steps:
      - uses: SuffolkLITLab/ALActions/hall_monitor@main
        with:
          SERVER_URL: "https://my-docassemble.example.com"
          MAILGUN_API_KEY: ${{ secrets.MY_MAILGUN_API_KEY }}
          MAILGUN_DOMAIN: ${{ secrets.MY_MAILGUN_DOMAIN }}
          ERROR_FROM_EMAIL: Monitor <alert@example.com>
          ERROR_EMAILS: example@example.com,example2@example.com
```

### word_diff

Word-diff creates a report of the changes to any .docx files between `main` and the current
pull request, after converting the files to markdown

#### Usage

```yml
on:
  pull_request:
    paths:
      - '**/*.docx'

jobs:
  my-workflow:
    ...
    steps:
    - uses: SuffolkLITLab/ALActions/word_diff@main
```


## Development Details

Using [codeql-action](https://github.com/github/codeql-action) as
a template for this repo.

This repo is mostly composite actions, as opposed to javascript or docker actions.
Visit [Github's documentation on composite actions](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action) for more info.
