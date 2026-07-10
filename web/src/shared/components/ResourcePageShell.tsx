import { Button, Empty, Input, Spin } from "@douyinfe/semi-ui";
import { Search } from "lucide-react";
import { FormEvent, ReactNode } from "react";

type ResourceMetric = {
  label: string;
  value: ReactNode;
};

type ResourcePageShellProps = {
  searchPlaceholder: string;
  keyword: string;
  loading: boolean;
  metrics: ResourceMetric[];
  empty: boolean;
  emptyIcon: ReactNode;
  emptyTitle: string;
  page: number;
  rangeStart: number;
  rangeEnd: number;
  total: number;
  canGoBack: boolean;
  canGoNext: boolean;
  children: ReactNode;
  onKeywordChange: (keyword: string) => void;
  onSearch: () => void;
  onPrevious: () => void;
  onNext: () => void;
};

export function ResourcePageShell({
  searchPlaceholder,
  keyword,
  loading,
  metrics,
  empty,
  emptyIcon,
  emptyTitle,
  page,
  rangeStart,
  rangeEnd,
  total,
  canGoBack,
  canGoNext,
  children,
  onKeywordChange,
  onSearch,
  onPrevious,
  onNext,
}: ResourcePageShellProps) {
  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSearch();
  };

  return (
    <section className="resource-page">
      <MetricStrip metrics={metrics} />

      <div className="table-panel">
        <form className="table-toolbar" onSubmit={handleSearch}>
          <Input
            prefix={<Search size={16} />}
            value={keyword}
            onChange={onKeywordChange}
            placeholder={searchPlaceholder}
            showClear
          />
          <Button htmlType="submit" theme="solid" type="primary" icon={<Search size={16} />}>
            Search
          </Button>
        </form>

        <Spin spinning={loading} wrapperClassName="resource-table-spin">
          {empty ? <Empty className="empty-state" image={emptyIcon} title={emptyTitle} description="" /> : children}
        </Spin>

        <div className="pager-row">
          <span>
            Page {page} · {rangeStart}-{rangeEnd} of {total}
          </span>
          <div>
            <Button type="tertiary" disabled={!canGoBack || loading} onClick={onPrevious}>Previous</Button>
            <Button type="tertiary" disabled={!canGoNext || loading} onClick={onNext}>Next</Button>
          </div>
        </div>
      </div>
    </section>
  );
}

export function MetricStrip({ metrics }: { metrics: ResourceMetric[] }) {
  return (
    <div className="metric-strip">
      {metrics.map((metric) => (
        <div className="metric-card" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </div>
  );
}
