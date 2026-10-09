// Decompiles the functions at the given addresses (hex, +-separated) to a file. Args: <addrs> <out>
// @category Sluggers

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

import java.io.PrintWriter;

public class ExportSome extends GhidraScript {
	@Override
	protected void run() throws Exception {
		String[] addrs = getScriptArgs()[0].split("[+]");
		DecompInterface di = new DecompInterface();
		di.openProgram(currentProgram);
		try (PrintWriter w = new PrintWriter(getScriptArgs()[1], "UTF-8")) {
			for (String a : addrs) {
				Function f = getFunctionContaining(toAddr(Long.parseLong(a, 16)));
				if (f == null) { w.println("// no function at " + a); continue; }
				DecompileResults r = di.decompileFunction(f, 60, monitor);
				w.println("//== " + f.getEntryPoint() + " " + f.getName(true));
				w.println(r != null && r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// failed");
			}
		}
		di.dispose();
	}
}
