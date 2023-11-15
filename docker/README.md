# Xsmall

This README aims at documenting the various hacks and tricks behind the `Dockerfile_cellxgene` to make a lightweight image for cellxgene

The image can be generated using the following command
```bash
docker build . -f Dockerfile_cellxgene -t cellxgene:xsmall
```

**Squash:** A note about squashing. docker build command used to provide a --squash parameter to avoid packing intermediate layers in the final image (resulting in way higher size). Now that docker moved to BuildKit this feature is not available anymore.

The alternative is to do a multi-stage build and use this for the last stage, assuming the second to last stage is called `final`:

```dockerfile
FROM scratch
COPY --from=final / /
```

## Build

### Numpy and numba

It is important that numpy is installed before numba (or the dependencies from `requirements.txt` including both packages) so that we can add its static libraries to the path. Else numba install will fail.

It is important to note that locale header must be linked **before** numpy install, and that numpy includes shared libraries must be linked afterwards, else numba build fails.

### Target

By providing the flag `-t path/to/directory` to a `pip setup.py install` command, we direct all files of the package **and its dependencies** into the directory.

The resulting directory looks like this

```bash
directory/
├── aiobotocore
│   ├── args.py
│   ├── awsrequest.py
│   └── waiter.py
├── ....
├── bin
│   ├── cellxgene
│   ├── f2py
│   └── ...
├── ...
├── numpy
│   └── ...
├── ...
├── yaml
│   └── ...
└── ...
```

From this point we may move the content of `bin` in one of the standard binary path (e.g. `/usr/local/bin`) and the rest under one of the python site-packages location (e.g. `/usr/local/lib/python3.11/site-packages/`)

## Static libraries

Static libraries used at runtime monitored using strace on a regular install

```bash
strace -ff -olog -eopen cellxgene launch --host 0.0.0.0 https://github.com/chanzuckerberg/cellxgene/raw/main/example-dataset/pbmc3k.h5ad
```

It will generate a bunch of files taking the form `log.[1-9]*` then you may go over the infos using this kind of commands

Note: grep -v excludes patterns. So you may iteratively add excluding patterns to get a finer grain

```bash
grep '\.so' log.* | grep -v 'site-packages'
grep '\.so' log.* | grep -v 'site-packages' | grep -v 'lib-dynload' | grep -v '= -1'
```

Of this list we copy the ones that are not natively present in the python alpine docker image
