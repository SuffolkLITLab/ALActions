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

### word_diff

`word_diff` converts any changed `.docx` files into Markdown (without introducing extra hard line wraps), diffing the rendered text so reviewers can read the changes directly in GitHub.

#### Usage

```yml
on:
  pull_request:
  workflow_dispatch:

jobs:
  docx-review:
    runs-on: ubuntu-latest
    steps:
      - name: Diff Word documents
        uses: SuffolkLITLab/ALActions/word_diff@main
        with:
          # Optional: override the base commit if needed
          # base_ref: main
          artifact_name: word-doc-diff
          output_dir: word_diffs
          summary_file: word_diff_summary.md
```

- Unified diffs are written to the job log and appended to the GitHub Actions step summary so you can skim changes without downloading artifacts.
- HTML side-by-side diffs, plus the converted Markdown files, are uploaded as an artifact (with an `index.html` table of contents by default) for richer review.
- The action automatically determines the correct comparison commits for pull requests and pushes. For manually dispatched runs, supply `base`/`head` inputs on the workflow or pass a `base_ref` input to the action directly.
- To make the diff run on every push, add a `push` trigger to your workflow or follow the pattern in `.github/workflows/word_diff.yml` to toggle push/PR execution via environment variables.

### valid_jinja2

`valid_jinja2` validates DOCX templates to ensure all embedded Jinja2 expressions have valid syntax. It checks both newly added and modified `.docx` files, distinguishing between syntax errors (which fail the build) and unknown filters (which generate warnings).

#### Key Features

- **Syntax Validation**: Ensures all Jinja2 blocks (`{{ }}`, `{% %}`) have correct syntax
- **Smart Filter Handling**: Recognizes 70+ common Docassemble and Jinja2 filters, treating unknown filters as warnings rather than errors
- **Comprehensive Reporting**: Generates HTML artifacts and Markdown summaries for easy review
- **Git Integration**: Automatically detects added and changed DOCX files in commits and pull requests

#### Sample Workflow

Create `.github/workflows/validate-docx.yml` in your repository:

```yml
name: Validate DOCX Templates

on:
  pull_request:
    paths:
      - '**/*.docx'
  push:
    branches:
      - main
    paths:
      - '**/*.docx'
  workflow_dispatch:

jobs:
  validate-docx:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Needed for git diff comparison
          
      - name: Validate DOCX Jinja2 templates
        uses: SuffolkLITLab/ALActions/valid_jinja2@main
        with:
          # Optional: customize artifact and output names
          artifact_name: jinja-validation-report
          output_dir: jinja_validation
          summary_file: jinja_validation_summary.md
```

#### Input Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `base_ref` | Git reference for comparison base | Auto-detected from event | No |
| `artifact_name` | Name for the uploaded validation artifact | `jinja-validation` | No |
| `output_dir` | Directory for HTML validation reports | `jinja_validation` | No |
| `summary_file` | Path for Markdown summary file | `jinja_validation_summary.md` | No |

#### Behavior

- **Syntax Errors**: Invalid Jinja2 syntax causes the workflow to fail
- **Unknown Filters**: Unrecognized filters generate warnings but don't fail the build
- **Known Filters**: Common Docassemble filters (like `currency`, `date`, `title_case`) don't generate warnings
- **Artifacts**: Only generated when there are validation issues (errors, warnings, or missing files)
- **Summary**: Always creates a Markdown summary showing validation results for each file

Artifacts should be visible in the Summary of the action results.

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
