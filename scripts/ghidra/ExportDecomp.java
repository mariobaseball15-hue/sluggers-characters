// Decompiles every function into one text file, each prefixed by "//== <entry> <name>".
// @category Sluggers

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

import java.io.PrintWriter;

public class ExportDecomp extends GhidraScript {
	@Override
	protected void run() throws Exception {
		String out = getScriptArgs().length > 0 ? getScriptArgs()[0] : "decomp.c";
		DecompInterface di = new DecompInterface();
		di.openProgram(currentProgram);
		int ok = 0, failed = 0;
		try (PrintWriter w = new PrintWriter(out, "UTF-8")) {
			for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
				if (monitor.isCancelled()) break;
				DecompileResults r = di.decompileFunction(f, 60, monitor);
				w.println("//== " + f.getEntryPoint() + " " + f.getName(true));
				if (r != null && r.decompileCompleted()) {
					w.println(r.getDecompiledFunction().getC());
					ok++;
				} else {
					w.println("// decompile failed: " + (r == null ? "null" : r.getErrorMessage()));
					failed++;
				}
			}
		}
		di.dispose();
		println("decompiled " + ok + " functions, " + failed + " failed, to " + out);
	}
}
