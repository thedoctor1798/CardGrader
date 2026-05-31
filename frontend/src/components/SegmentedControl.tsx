type SegmentedOption<T extends string> = {
  value: T;
  label: string;
  disabled?: boolean;
};

type SegmentedControlProps<T extends string> = {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
};

export function SegmentedControl<T extends string>({ options, value, onChange, className = "" }: SegmentedControlProps<T>) {
  return (
    <div className={`control-surface flex gap-1 overflow-x-auto rounded-2xl p-1 ${className}`}>
      {options.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.value}
            className={`min-h-10 shrink-0 rounded-xl px-3 py-2 text-sm font-medium transition disabled:opacity-40 ${
              active
                ? "bg-gradient-to-br from-cyan-300/90 to-teal-300/90 text-slate-950 shadow-[0_8px_22px_rgba(45,212,191,0.2)]"
                : "text-slate-300 hover:bg-white/10 hover:text-slate-100"
            }`}
            disabled={option.disabled}
            onClick={() => onChange(option.value)}
            type="button"
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
