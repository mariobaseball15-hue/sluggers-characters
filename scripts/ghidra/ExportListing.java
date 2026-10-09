// Dumps every instruction as: address, function entry, function name, instruction text.
// @category Sluggers

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

import java.io.PrintWriter;

public class ExportListing extends GhidraScript {
	@Override
	protected void run() throws Exception {
		String out = getScriptArgs().length > 0 ? getScriptArgs()[0] : "listing.tsv";
		int n = 0;
		try (PrintWriter w = new PrintWriter(out, "UTF-8")) {
			for (Instruction ins : currentProgram.getListing().getInstructions(true)) {
				Function f = getFunctionContaining(ins.getAddress());
				w.println(ins.getAddress() + "\t" + (f == null ? "-" : f.getEntryPoint()) + "\t"
					+ (f == null ? "-" : f.getName(true)) + "\t" + ins);
				n++;
			}
		}
		println("wrote " + n + " instructions to " + out);
	}
}
