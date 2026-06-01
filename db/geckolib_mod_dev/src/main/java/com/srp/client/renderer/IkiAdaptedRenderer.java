package com.srp.client.renderer;

import com.srp.client.model.IkiAdaptedModel;
import com.srp.entity.IkiAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class IkiAdaptedRenderer extends GeoEntityRenderer<IkiAdaptedEntity> {

    public IkiAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new IkiAdaptedModel());
    }
}
