import * as React from "react"
import { ArrowRight, ArrowUpRight, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Evidence } from "@/components/evidence"
import { ContractDetail } from "@/components/detail-panel"
import { relationWords } from "@/relations"
import { localizeNote, STRINGS } from "@/i18n"
import type { MapLink } from "@/types"
import type { Model } from "@/model"

export function RelationPanel({
  model,
  links,
  onNavigate,
  onClose,
}: {
  model: Model
  links: MapLink[]
  onNavigate: (id: string) => void
  onClose: () => void
}) {
  const [index, setIndex] = React.useState(0)
  const link = links[index] ?? links[0]
  const words = relationWords[model.lang]
  const t = STRINGS[model.lang]
  const target = model.flowById.get(link.target.flow_id)?.flow
  const entry = target?.steps?.find((step) => step.kind === "trigger")
  return (
    <Card className="h-full min-h-0 gap-0 rounded-2xl py-0 shadow-[var(--shadow-float)]">
      <CardHeader className="gap-3 p-5 pb-4">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-base leading-6">{link.name}</CardTitle>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t.close}
            onClick={onClose}
          >
            <X />
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{words.kind[link.relation]}</Badge>
          <Badge variant="outline">
            {link.resolution === "candidate" ? words.pending : words.confirmed}
          </Badge>
        </div>
      </CardHeader>
      <Tabs defaultValue="overview" className="min-h-0 flex-1 gap-0">
        <div className="border-b border-line px-5">
          <TabsList variant="line" className="h-10 gap-5 p-0">
            <TabsTrigger value="overview" className="px-0">
              {words.overview}
            </TabsTrigger>
            <TabsTrigger value="contract" className="px-0">
              {t.ioContract}
            </TabsTrigger>
          </TabsList>
        </div>
        <ScrollArea className="min-h-0 flex-1">
          <div className="p-5">
            <TabsContent value="overview" className="space-y-5">
              {links.length > 1 && (
                <div className="flex flex-col gap-1">
                  {links.map((item, i) => (
                    <Button
                      key={item.link_id}
                      variant={index === i ? "secondary" : "ghost"}
                      className="h-auto min-h-8 justify-start text-left text-[13px] whitespace-normal"
                      onClick={() => setIndex(i)}
                    >
                      {item.name}
                    </Button>
                  ))}
                </div>
              )}
              <div className="space-y-4">
                {(["source", "target"] as const).map((side) => {
                  const flow = model.flowById.get(link[side].flow_id)?.flow
                  const module = model.moduleOf.get(link[side].flow_id)
                  const step = flow?.steps?.find(
                    (item) => item.step_id === link[side].step_id
                  )
                  return (
                    <section key={side} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-ink-3">
                          {side === "source" ? words.caller : words.target}
                        </span>
                        <span className="text-xs text-ink-3">
                          {module?.name}
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        className="-ml-2 h-auto min-h-8 max-w-full justify-start px-2 text-left whitespace-normal"
                        onClick={() => onNavigate(link[side].flow_id)}
                      >
                        {flow?.name}
                        <ArrowUpRight />
                      </Button>
                      {step && step.kind !== "trigger" && (
                        <p className="text-[13px] text-ink-2">{step.name}</p>
                      )}
                      {side === "source" && (
                        <ArrowRight className="size-4 rotate-90 text-ink-3" />
                      )}
                    </section>
                  )
                })}
              </div>
              {link.reason && (
                <p className="text-[13px] leading-6 text-ink-2">
                  {localizeNote(link.reason, model.lang)}
                </p>
              )}
              <Separator />
              <section className="space-y-3">
                <h3 className="text-sm font-medium">{words.evidence}</h3>
                <Evidence
                  ids={[
                    ...new Set([
                      ...(link.source_evidence_ids ?? []),
                      ...(link.target_evidence_ids ?? []),
                    ]),
                  ]}
                  model={model}
                  t={t}
                />
              </section>
            </TabsContent>
            <TabsContent value="contract">
              <p className="mb-4 text-xs text-ink-3">{target?.name}</p>
              {entry?.contract ? (
                <ContractDetail contract={entry.contract} t={t} />
              ) : (
                <p className="text-sm leading-6 text-ink-2">
                  {words.noContract}
                </p>
              )}
            </TabsContent>
          </div>
        </ScrollArea>
      </Tabs>
    </Card>
  )
}
