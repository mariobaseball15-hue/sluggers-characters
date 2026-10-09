// Applies names from build_names.py (kind, address, namespace path, name) and sets the small-data base
// registers (r2 = _SDA2_BASE_, r13 = _SDA_BASE_) so globals read as addresses, not unaff_r13 + offset.
// Methods go into class namespaces with __thiscall, so the decompiler shows `this` as the class.
// @category Sluggers

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.ProgramContext;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Namespace;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;
import ghidra.program.model.symbol.SymbolType;
import ghidra.app.util.NamespaceUtils;
import ghidra.program.model.data.Structure;
import ghidra.program.model.listing.GhidraClass;
import ghidra.program.model.listing.VariableUtilities;

import java.io.BufferedReader;
import java.io.FileReader;
import java.math.BigInteger;
import java.util.HashMap;
import java.util.Map;

public class ApplyNames extends GhidraScript {
	private final Map<String, Namespace> cache = new HashMap<>();

	private Namespace ns(String path, boolean lastIsClass) throws Exception {
		if (path.isEmpty()) return currentProgram.getGlobalNamespace();
		String key = path + (lastIsClass ? "#c" : "");
		Namespace hit = cache.get(key);
		if (hit != null) return hit;
		SymbolTable st = currentProgram.getSymbolTable();
		Namespace parent = currentProgram.getGlobalNamespace();
		String[] parts = path.split("::(?![^<]*>)");
		for (int i = 0; i < parts.length; i++) {
			boolean cls = lastIsClass && i == parts.length - 1;
			Namespace n = st.getNamespace(parts[i], parent);
			if (n == null) {
				n = cls ? st.createClass(parent, parts[i], SourceType.IMPORTED)
					: st.createNameSpace(parent, parts[i], SourceType.IMPORTED);
			} else if (cls && n.getSymbol().getSymbolType() != SymbolType.CLASS) {
				n = NamespaceUtils.convertNamespaceToClass(n);
			}
			parent = n;
		}
		cache.put(key, parent);
		return parent;
	}

	@Override
	protected void run() throws Exception {
		String tsv = getScriptArgs()[0];

		ProgramContext ctx = currentProgram.getProgramContext();
		Register r2 = currentProgram.getRegister("r2"), r13 = currentProgram.getRegister("r13");
		for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
			if (!b.isExecute()) continue;
			ctx.setValue(r2, b.getStart(), b.getEnd(), BigInteger.valueOf(0x8079EDC0L));
			ctx.setValue(r13, b.getStart(), b.getEnd(), BigInteger.valueOf(0x807961C0L));
		}

		int fns = 0, labels = 0, created = 0, failed = 0, sizes = 0;
		try (BufferedReader r = new BufferedReader(new FileReader(tsv))) {
			String line;
			while ((line = r.readLine()) != null) {
				String[] f = line.split("\t", -1);
				if (f.length < 4) continue;
				String kind = f[0], path = f[2], name = f[3].replace(' ', '_');
				Address a = toAddr(Long.parseLong(f[1], 16));
				try {
					if (kind.equals("size")) {
						// Size the class's struct so the decompiler prints this->field_0x18, not this[0x18].
						GhidraClass c = (GhidraClass) ns(path, true);
						Structure st = VariableUtilities.findOrCreateClassStruct(c, currentProgram.getDataTypeManager());
						int n = Integer.parseInt(name);
						if (st.getLength() < n) {
							if (st.isZeroLength()) st.growStructure(n); else st.growStructure(n - st.getLength());
						}
						sizes++;
						continue;
					}
					if (kind.equals("label")) {
						Symbol s = currentProgram.getSymbolTable().createLabel(a, name, ns(path, true), SourceType.IMPORTED);
						s.setPrimary();
						labels++;
						continue;
					}
					Function fn = getFunctionAt(a);
					if (fn == null) {
						fn = createFunction(a, null);
						if (fn == null) { failed++; continue; }
						created++;
					}
					boolean method = kind.equals("method");
					fn.setParentNamespace(ns(path, method));
					fn.setName(name, SourceType.IMPORTED);
					if (method) {
						try {
							fn.setCallingConvention("__thiscall");
						} catch (Exception e) {
							// processor has no thiscall model; the class namespace still names it
						}
					}
					fns++;
				} catch (Exception e) {
					failed++;
					if (failed <= 20) println("failed " + line + ": " + e.getMessage());
				}
			}
		}
		println("named " + fns + " functions (" + created + " created), " + labels + " labels, " + sizes + " class sizes, " + failed + " failed");
	}
}
