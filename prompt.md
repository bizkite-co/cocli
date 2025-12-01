I have moved the  to @docs/data-manager-design/_index.md. The Data Type Awareness segment is a little vague. I think we need to create a Pydantic data model for all stored types, not just Company. Anything that is stored to a CSV should be stored in a type with CSV in it.

So, the type of data written to the GoogleMapsData CSV should be a GoogleMapsDataCSV Pydantic data type. It should be a one-to-one mapping to the CSV headers. Any transformation to another data type should be handled by an explicit mapping. I think we described that in the @docs/adr/from-model-to-model.md document and a couple other places. We need to add diagrams and other supporting docs to the same folder. 

Can we hadd a ERD or C4 Mermaid or Plant UML document for the data manager? What is the bucket name we should check for new content?
