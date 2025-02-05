#!/bin/sh

# PROVIDE: sopel
# REQUIRE: FILESYSTEM NETWORKING usr

. /etc/rc.subr

name="sopel"
desc="Simple, easy-to-use, open-source IRC utility bot, written in Python"
rcvar="${name}_enable"
start_cmd="sopel_start"
stop_cmd="sopel_stop"
restart_cmd="sopel_restart"
status_cmd="sopel_status"
configure_cmd="sopel_configure"
extra_commands="configure"

load_rc_config "${name}"

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

sopel_start()
{
	local profile

	profile="$1"; shift

	echo "Starting sopel profile '${profile}'." && sleep 1
        /usr/sbin/daemon \
		-o "${sopel_output}" \
		-t "${desc}" \
		-u "${sopel_user}" \
		${sopel_interpreter} \
		${sopel_program} start ${sopel_flags} \
			-c "${sopel_prefix}${profile}" $@
}

sopel_stop()
{
	local pid pidfile profile
	
	profile="$1"; shift

	pidfile="${sopel_piddir}/${sopel_prefix}${sopel_prefix}${profile}.pid"
	if ! [ -f "${pidfile}" ]; then
		return 1
	fi

	pid=`cat ${pidfile}`

	echo "Stopping sopel profile '${profile}'."
        /usr/sbin/daemon \
		-o "${sopel_output}" \
		${sopel_interpreter} \
		${sopel_program} stop ${sopel_flags} \
			-c "${sopel_prefix}${profile}" $@

	wait_for_pids $pid
}

sopel_restart()
{
	local profile
	
	profile="$1"; shift

        run_rc_command stop "${profile}" $@ &&
        sleep 1 &&
        run_rc_command start "${profile}" $@
}

sopel_status()
{
	local profile pid

	profile="$1"; shift

	pid=`check_pidfile \
		"${sopel_piddir}/${sopel_prefix}${sopel_prefix}${profile}.pid" \
		"${sopel_program}" \
		"${sopel_interpreter}"`

	if [ -n "${pid}" ]; then
		echo "Sopel profile '${profile}' is running as pid ${pid}."
	else
		echo "Sopel profile '${profile}' is not running."
	fi
}

sopel_configure()
{
	local profile

	profile="$1"; shift

	echo "Configuring profile '${profile}'..."

	${sopel_interpreter} \
        ${sopel_program} configure ${sopel_flags} \
		-c "${sopel_confdir}/${sopel_prefix}${profile}" $@
}

cmd="$1"; shift
for profile in $sopel_profiles; do
	if ! [ -f "${sopel_confdir}/${sopel_prefix}${profile}.cfg" ]; then
		echo "Sopel profile '${profile}' does not exist."
		continue
	fi

	run_rc_command "${cmd}" "${profile}" $@
done
