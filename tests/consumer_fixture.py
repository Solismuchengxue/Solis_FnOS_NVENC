"""Real local FIFO process tree for consumer-guard regression tests."""
import json,pathlib,sys,time

HELPER='''set -eu
work=$(mktemp -d)
resource=$1
shift
readers=''
cleanup() { for pid in $readers; do kill "$pid" 2>/dev/null || :; wait "$pid" 2>/dev/null || :; done; rm -f "$work"/*; rmdir "$work"; }
trap cleanup 0
for name in sudo_out sudo_err target_out target_err; do mkfifo "$work/$name"; done
capture() {
 fifo=$1
 label=$2
 ( exec 3< "$fifo"
   if [ "$resource" != '-' ]; then exec 6< "$resource"; fi
   payload=$(head -c 262144 <&3 | base64 | tr -d '\\r\\n')
   printf '%s %s\\n' "$label" "$payload"
 ) &
 readers="$readers $!"
}
capture "$work/sudo_out" SUDO_OUT
capture "$work/sudo_err" SUDO_ERR
capture "$work/target_out" TARGET_OUT
capture "$work/target_err" TARGET_ERR
exec 4> "$work/sudo_out"
exec 5> "$work/sudo_err"
"$@" </dev/null > "$work/target_out" 2> "$work/target_err"
exec 4>&-
exec 5>&-
for pid in $readers; do wait "$pid"; done
readers=''
'''

def probe():
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
    config=json.loads(pathlib.Path(sys.argv[1]).read_text());roots=[pathlib.Path(x) for x in sys.argv[2:4]]
    from nvenc_consumers import ProcFS,assert_no_consumers
    class FixtureProc(ProcFS):
        def pids(self):
            selected=[]
            for p in pathlib.Path('/proc').glob('[0-9]*'):
                try:
                    # Scope the test to its own real processes, not unrelated host users.
                    raw=p.joinpath('cmdline').read_bytes()
                    if config['marker'].encode() in raw:selected.append(int(p.name))
                except (FileNotFoundError,ProcessLookupError,PermissionError):pass
            return selected
    try:
        time.sleep(0.15)  # Let all four FIFO readers acquire their real descriptors.
        result=assert_no_consumers(roots,config['helper_argv'],config['helper_exe_sha256'],FixtureProc())
        print(json.dumps(result))
    except Exception as e:print(json.dumps({'result':'REFUSED','error':str(e)}))

if __name__=='__main__':probe()
