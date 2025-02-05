This folder contains `sopel` and `sopel-default.cfg` designed to be distributed by third parties such as FreeBSD.

`sopel-default.cfg` is a default configuration file for sopel.

The -default prefix is mandatory and will be used as a 'profile'.

The profiles started by the service may be changed with the variable `sopel_profiles` in `/etc/rc.conf`, or with the `sysrc` command:

```sh
sysrc sopel_profiles="profile1 profile2 profile3"
```

By default, the configuration directory is `/usr/local/etc`.

For the above example, the configuration files `sopel-profile1.cfg`, `sopel-profile2.cfg`, and `sopel-profile3.cfg` must be present there.

The service must be installed in `/usr/local/etc/rc.d`:

```sh
cp sopel.sh /usr/local/etc/rc.d/sopel
chmod +x /usr/local/etc/rc.d/sopel
```

The default configuration file must be installed in the configuration directory as another profile. For example:

```sh
cp sopel-default.cfg /usr/local/etc
```

That configuration has the variables `logdir`, `homedir` and `pid_dir`.

You must create `homedir`, `logdir` and `pid_dir` directories:

```sh
mkdir -p path/to/homedir
mkdir -p path/to/logdir
mkdir -p path/to/pid_dir
```

The service file has a variable named `sopel_user` (by default, the value is `sopel`). You must create that user before starting sopel.

After creating the user for sopel, you must change the owner of the `logdir`, `pid_dir` and `homedir` directories:

```sh
chown sopel:sopel path/to/logdir
chown sopel:sopel path/to/pid_dir
chown sopel:sopel path/to/homedir
```

If you want to run sopel at startup, the variable `sopel_enable` must be set to `YES`:

```sh
sysrc sopel_enable="YES"
```

Now, you can run the service with the `service(8)` command, but if you want to change any options, you can do so by editing the `sopel-default.cfg` configuration file or by using `service sopel configure`. When sopel is configured, it can be started:

```sh
service sopel start
```

If you want to change the python version, the variable `sopel_interpreter` must be changed. For example:

```sh
sysrc sopel_interpreter="/usr/local/bin/python3.8"
```

You can set any other variable, but by default, the sopel service has many default values:

```sh
$ egrep -E '^: \$\{sopel_.+:=.+}' sopel
: ${sopel_enable:="NO"}
: ${sopel_piddir:="/var/run/sopel"}
: ${sopel_confdir:=/usr/local/etc}
: ${sopel_flags:=--config-dir "${sopel_confdir}"}
: ${sopel_program:="/usr/local/bin/sopel"}
: ${sopel_user:=${name}}
: ${sopel_interpreter:=/usr/local/bin/python3.9}
: ${sopel_profiles:=default}
: ${sopel_prefix:=sopel-}
: ${sopel_output:=/dev/null}
```
