# Read after an application's Makefile by the tests of step G0-3: prints the
# expanded value of each variable of G003_NAMES (passed on the command line)
# and, as the recipe of riot-g003-env, the environment Make exports.
$(foreach v,$(G003_NAMES),$(info G003 $v = $(strip $($v))))
riot-g003-env:
	@env | LC_ALL=C sort | sed 's/^/ENV /'
