# ALActions - Github Actions for the Assembly Line project

Shared actions, used over many different [Assembly Line projets](https://suffolklitlab.org/docassemble-AssemblyLine-documentation/docs/).

## Usage

You can use the actions in repo github workflows by refering to a specific branch or tag like this:

```yml
test-assemblyline:
    runs-on: ubuntu-latest
    name: Run python only unit tests
    steps:
      - uses: SuffolkLITLab/ALActions/pythontests@main 
```

For assembly line projects, you should refer to the `main` branch, as that will allow 
bug fixes to the actions to immediately propagate to the AssemblyLine repos.

## The Actions

* `pythontest`: sets up a python environment around the package, and runs any `unittest` tests in the package.
* `publish` (not yet in use): publish a python package to pypi, and announce the publishing to the Assembly Line Teams chat.

## Details

Using [codeql-action](https://github.com/github/codeql-action) as
a template for this repo.

This repo is mostly composite actions, as opposed to javascript or docker actions for now.
Visit [Github's documentation on composite actions](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action) for more info.
