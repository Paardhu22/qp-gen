"use client";

import * as React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { HeaderDetail } from "./header-details";

export function HeaderDetailsEditor({ schoolName, showSchoolName, fields, hiddenFields, showDate, dateValue, onClose, onApply }: {
  schoolName: string; showSchoolName: boolean;
  fields: HeaderDetail[]; hiddenFields: string[]; showDate: boolean; dateValue: string;
  onClose: () => void;
  onApply: (attrs: { schoolName: string; showSchoolName: boolean; details: HeaderDetail[]; hiddenFields: string[]; showDate: boolean; dateValue: string }) => void;
}) {
  const [name, setName] = React.useState(schoolName);
  const [nameEnabled, setNameEnabled] = React.useState(showSchoolName);
  const [details, setDetails] = React.useState(fields);
  const [hidden, setHidden] = React.useState(hiddenFields);
  const [dateEnabled, setDateEnabled] = React.useState(showDate);
  const [date, setDate] = React.useState(dateValue);
  const prefix = React.useId();
  return (
    <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-lg font-sans text-foreground">
        <form className="min-w-0 space-y-5" onSubmit={event => {
          event.preventDefault();
          onApply({ schoolName: name, showSchoolName: nameEnabled, details, hiddenFields: hidden, showDate: dateEnabled, dateValue: date });
        }}>
          <DialogHeader className="pr-6">
            <DialogTitle>Edit paper header</DialogTitle>
            <DialogDescription>Choose what appears on the paper. Empty or unchecked details are left out.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid min-w-0 grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-3">
              <label className="flex min-h-11 items-center gap-2 text-sm" htmlFor={`${prefix}-school-enabled`}>
                <input id={`${prefix}-school-enabled`} type="checkbox" checked={nameEnabled} className="h-4 w-4 accent-primary" onChange={event => setNameEnabled(event.target.checked)} />
                School name
              </label>
              <Input aria-label="School name value" disabled={!nameEnabled} value={name} placeholder="School name" onChange={event => setName(event.target.value)} />
            </div>
            {details.map((field, index) => {
              const enabled = !hidden.includes(field.id);
              const inputId = `${prefix}-${field.id}`;
              return (
                <div key={field.id} className="grid min-w-0 grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-3">
                  <label className="flex min-h-11 items-center gap-2 text-sm" htmlFor={`${inputId}-enabled`}>
                    <input id={`${inputId}-enabled`} type="checkbox" checked={enabled} className="h-4 w-4 accent-primary" onChange={event => {
                      setHidden(current => event.target.checked ? current.filter(id => id !== field.id) : [...current, field.id]);
                    }} />
                    {field.label}
                  </label>
                  <Input id={inputId} aria-label={`${field.label} value`} disabled={!enabled} value={field.value} placeholder={field.id === "time" ? "e.g. 90 minutes" : field.id === "set" ? "e.g. A" : field.label} onChange={event => {
                    setDetails(current => current.map((item, i) => i === index ? { ...item, value: event.target.value } : item));
                  }} />
                </div>
              );
            })}
            <div className="grid grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-3">
              <label className="flex min-h-11 items-center gap-2 text-sm" htmlFor={`${prefix}-date-enabled`}>
                <input id={`${prefix}-date-enabled`} type="checkbox" checked={dateEnabled} className="h-4 w-4 accent-primary" onChange={event => setDateEnabled(event.target.checked)} />
                Paper date
              </label>
              <Input type="date" aria-label="Paper date value" disabled={!dateEnabled} value={date} onChange={event => setDate(event.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit">Apply header</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
