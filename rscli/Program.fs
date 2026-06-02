open System
open System.IO
open Rocksmith2014.Common
open Rocksmith2014.XML
open Rocksmith2014.SNG
open Rocksmith2014.Conversion

let usage () =
    printfn "Usage:"
    printfn "  RsCli xml2sng <input.xml> <output.sng>"
    printfn "  RsCli sng2xml <input.sng> <output.xml> [pc|mac]"
    printfn ""
    printfn "Converts between Rocksmith 2014 arrangement XML and encrypted SNG."
    1

let xml2sng (xmlPath: string) (sngPath: string) =
    async {
        printfn "Loading XML: %s" xmlPath
        let xml = InstrumentalArrangement.Load(xmlPath)
        printfn "Converting to SNG (%d notes)..." xml.Levels.[0].Notes.Count
        let sng = ConvertInstrumental.xmlToSng xml
        let dir = Path.GetDirectoryName(sngPath)
        if not (String.IsNullOrEmpty(dir)) then
            Directory.CreateDirectory(dir) |> ignore
        printfn "Saving encrypted SNG: %s" sngPath
        do! SNG.savePackedFile sngPath Platform.PC sng
        printfn "Done."
    }
    |> Async.RunSynchronously
    0

let sng2xml (sngPath: string) (xmlPath: string) (platform: Platform) =
    async {
        printfn "Loading SNG (%A): %s" platform sngPath
        let! sng = SNG.readPackedFile sngPath platform
        printfn "Converting to XML..."
        let xml = ConvertInstrumental.sngToXml None sng
        let dir = Path.GetDirectoryName(xmlPath)
        if not (String.IsNullOrEmpty(dir)) then
            Directory.CreateDirectory(dir) |> ignore
        xml.Save(xmlPath)
        printfn "Saved XML: %s" xmlPath
    }
    |> Async.RunSynchronously
    0

[<EntryPoint>]
let main argv =
    match argv |> Array.toList with
    | "xml2sng" :: xmlPath :: sngPath :: _ ->
        try xml2sng xmlPath sngPath
        with ex ->
            eprintfn "Error: %s" ex.Message
            eprintfn "%s" ex.StackTrace
            1
    | "sng2xml" :: sngPath :: xmlPath :: rest ->
        try
            let platform =
                match rest with
                | p :: _ when p.ToLowerInvariant() = "mac" -> Platform.Mac
                | _ -> Platform.PC
            sng2xml sngPath xmlPath platform
        with ex ->
            eprintfn "Error: %s" ex.Message
            eprintfn "%s" ex.StackTrace
            1
    | _ ->
        usage ()
